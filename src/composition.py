"""Racine de composition : le SEUL module autorisé à importer ``agent`` ET
``executor``. Instancie les vraies implémentations (LLM réel, flux, stores
persistants, exécuteur réel) et câble les pipelines. Aucun secret n'est codé
ici : tout vient de ``Settings`` (donc de l'environnement).
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
from core.usage import ListUsageSink
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
from radar.observability.history import JsonRunHistoryStore
from radar.observability.models import RunRecord
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
# Bundle de CA certifi plutôt que le magasin par défaut de l'OS : certains
# flux (ex. blog.n8n.io) échouent la validation TLS avec le contexte SSL par
# défaut de Python sur cette machine (chaîne de certification non résolue).
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_MAX_AGE = timedelta(days=7)
_TOP_K = 5
_MAX_SCORED = 30
_MIN_SCORE = 8  # calibré module 3.5 : voir QUALITY.md (precision/recall par seuil)
_MAX_HISTORY_TURNS = 20
_LLM_MAX_TOKENS = 512  # marge pour le drafting ; le scoring reste court de fait
_MAX_CONCURRENCY = 5  # défaut prudent, cf. CONCURRENCY.md


def build_radar_pipeline(settings: Settings) -> Callable[[], RunRecord]:
    """Câble le workflow radar de production avec les vraies implémentations.

    Chemin unique depuis le module 4.5 (``MIGRATION.md``) : scoring
    concurrent borné (module 4.3) + drafting décomposé AngleAgent/
    WriterAgent (module 4.2) via ``build_radar_steps_production``.
    ``run_pipeline`` (module 1.x) a été supprimée — plus de voie morte.

    Le runner renvoie un ``RunRecord`` (rapport + usage LLM agrégé du run,
    horodaté) et l'archive dans l'historique persistant (module 3.4). Le
    ``PipelineReport`` qu'il contient a exactement le même schéma qu'avant
    cette migration (``radar_workflow_state_to_pipeline_report``) : aucune
    régression pour ``run_report.json``/``RunHistoryStore``.
    """
    usage_sink = ListUsageSink()
    llm = AnthropicClient(
        api_key=settings.anthropic_api_key,
        max_tokens=_LLM_MAX_TOKENS,
        usage_sink=usage_sink,
    )
    seen_store = JsonSeenStore(settings.store_dir / "seen.json")
    history_store = JsonRunHistoryStore(settings.store_dir / "run_history.json")
    fetch_items = _make_feed_fetcher(settings.feed_urls)
    concurrency_config = ConcurrentScoringConfig(max_concurrency=_MAX_CONCURRENCY)

    def run() -> RunRecord:
        usage_sink.calls.clear()
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
        )
        workflow_run = run_workflow(
            steps, RadarWorkflowState(), usage_sink=usage_sink
        )
        report = radar_workflow_state_to_pipeline_report(workflow_run.final_state)
        record = RunRecord(
            at=datetime.now(tz=UTC), report=report, usage=workflow_run.usage
        )
        history_store.append(record)
        return record

    return run


def build_agent(settings: Settings) -> Callable[[InboundMessage], AgentResult]:
    """Câble ``handle_message`` avec les vraies implémentations. Renvoie un runner."""
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
    """Câble l'exécuteur réel (sink + journal persistant). Renvoie un runner."""
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
                # skip + continue : un flux en échec ne doit pas tuer le run.
                continue
        return items

    return fetch
