"""Composition root: the ONLY module allowed to import ``agent`` AND
``executor``. Instantiates the real implementations (real LLM, feeds,
persistent stores, real executor) and wires the pipelines. No secret is
hard-coded here: everything comes from ``Settings`` (hence the environment).
"""
import ssl
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from xml.etree.ElementTree import ParseError

import certifi

from agent.agent.result import AgentResult
from agent.agent.runner import AgentConfig, handle_message
from agent.conversation.store import JsonConversationStore
from agent.intake.models import InboundMessage
from agent.tools.read import CrmReadTool, KnowledgeBaseReadTool
from agent.tools.registry import ReadToolRegistry
from core.usage import ListUsageSink, TeeUsageSink
from core.workflow.engine import run_workflow
from executor.execute import (
    ExecutionResult,
    JsonExecutionLedger,
    RecordingActionSink,
    execute,
)
from executor.models import ApprovedAction
from radar.concurrent_scoring import ConcurrentScoringConfig
from radar.domain import RawItem
from radar.llm.anthropic_client import AnthropicClient
from radar.llm.timing import CallTimeline
from radar.observability.history import JsonRunHistoryStore
from radar.observability.models import RunRecord
from radar.observability.trace import RadarRunOutcome, build_run_trace
from radar.pipeline import PipelineConfig
from radar.sources.rss import parse_rss
from radar.tools.seen_store import JsonSeenStore
from radar.workflow import (
    RadarWorkflowState,
    build_radar_steps_production,
    radar_workflow_state_to_pipeline_report,
)
from settings import Settings

_USER_AGENT = "Mozilla/5.0 (compatible; radar-automation/0.1; RSS reader)"
# certifi CA bundle rather than the OS default store: some feeds
# (e.g. blog.n8n.io) fail TLS validation with Python's default SSL
# context on this machine (certificate chain unresolved).
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_MAX_AGE = timedelta(days=7)
_TOP_K = 5
_MAX_SCORED = 30
_MIN_SCORE = 8  # calibrated in module 3.5, see QUALITY.md
_MAX_HISTORY_TURNS = 20
_LLM_MAX_TOKENS = 512  # headroom for drafting; scoring stays short anyway
_MAX_CONCURRENCY = 5  # prudent default, see CONCURRENCY.md


def build_radar_pipeline(settings: Settings) -> Callable[[], RadarRunOutcome]:
    """Wire the production radar workflow with the real implementations.

    Single path since module 4.5 (``MIGRATION.md``): bounded concurrent
    scoring (module 4.3) + decomposed AngleAgent/WriterAgent drafting
    (module 4.2) via ``build_radar_steps_production``. ``run_pipeline``
    (module 1.x) was removed — no more dead path.

    The runner returns a ``RadarRunOutcome``: the ``RunRecord`` (report +
    aggregated LLM usage of the run, timestamped), archived in the persistent
    history (module 3.4) with exactly the same schema as before — no
    regression for ``run_report.json``/``RunHistoryStore`` — **and** the
    detailed trace of the same run (module 4.6, ``OBSERVABILITY.md``), which
    lives in its own artifact rather than widening an existing contract.

    The ``TeeUsageSink`` is what lets the two usage consumers coexist
    without double counting: the ``ListUsageSink`` feeds the hard budget of
    concurrent scoring (module 4.3) and the ``RunRecord`` total, while the
    ``CallTimeline`` attributes the same usage to the LLM call that produced it.
    """
    usage_sink = ListUsageSink()
    timeline = CallTimeline()
    llm = AnthropicClient(
        api_key=settings.anthropic_api_key,
        max_tokens=_LLM_MAX_TOKENS,
        usage_sink=TeeUsageSink([usage_sink, timeline]),
    )
    seen_store = JsonSeenStore(settings.store_dir / "seen.json")
    history_store = JsonRunHistoryStore(settings.store_dir / "run_history.json")
    fetch_items = _make_feed_fetcher(settings.feed_urls)
    concurrency_config = ConcurrentScoringConfig(max_concurrency=_MAX_CONCURRENCY)

    def run() -> RadarRunOutcome:
        usage_sink.calls.clear()
        timeline.clear()
        config = PipelineConfig(
            now=datetime.now(tz=UTC),
            max_age=_MAX_AGE,
            k=_TOP_K,
            max_scored=_MAX_SCORED,
            min_score=_MIN_SCORE,
        )
        steps = build_radar_steps_production(
            fetch_items=fetch_items,
            seen_store=seen_store,
            llm=llm,
            config=config,
            concurrency_config=concurrency_config,
            usage_sink=usage_sink,
            timeline=timeline,
        )
        workflow_run = run_workflow(
            steps, RadarWorkflowState(), usage_sink=usage_sink
        )
        report = radar_workflow_state_to_pipeline_report(workflow_run.final_state)
        at = datetime.now(tz=UTC)
        record = RunRecord(at=at, report=report, usage=workflow_run.usage)
        history_store.append(record)
        return RadarRunOutcome(
            record=record,
            trace=build_run_trace(
                report=report,
                workflow_run=workflow_run,
                calls=timeline.snapshot(),
                run_at=at,
            ),
        )

    return run


def build_agent(settings: Settings) -> Callable[[InboundMessage], AgentResult]:
    """Wire ``handle_message`` with the real implementations. Returns a runner."""
    llm = AnthropicClient(
        api_key=settings.anthropic_api_key, max_tokens=_LLM_MAX_TOKENS
    )
    conversations = JsonConversationStore(settings.store_dir / "conversations.json")
    read_tools = ReadToolRegistry([CrmReadTool({}), KnowledgeBaseReadTool({})])
    config = AgentConfig(max_history_turns=_MAX_HISTORY_TURNS)

    def handle(msg: InboundMessage) -> AgentResult:
        return handle_message(
            msg=msg,
            conversations=conversations,
            read_tools=read_tools,
            llm=llm,
            config=config,
        )

    return handle


def build_executor(settings: Settings) -> Callable[[ApprovedAction], ExecutionResult]:
    """Wire the real executor (sink + persistent journal). Returns a runner."""
    sink = RecordingActionSink()
    ledger = JsonExecutionLedger(settings.store_dir / "executed.json")

    def run(action: ApprovedAction) -> ExecutionResult:
        return execute(action, sink=sink, ledger=ledger)

    return run


def _make_feed_fetcher(feed_urls: list[str]) -> Callable[[], list[RawItem]]:
    def fetch() -> list[RawItem]:
        items: list[RawItem] = []
        for url in feed_urls:
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": _USER_AGENT}
                )
                with urllib.request.urlopen(
                    request, context=_SSL_CONTEXT
                ) as response:
                    xml = response.read().decode("utf-8", errors="replace")
                items.extend(parse_rss(xml))
            except (OSError, ParseError):
                # skip + continue: a failing feed must not kill the run.
                continue
        return items

    return fetch
