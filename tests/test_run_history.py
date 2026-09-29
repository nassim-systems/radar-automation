from datetime import UTC, datetime
from pathlib import Path

from core.usage import LlmUsage
from radar.observability.history import InMemoryRunHistoryStore, JsonRunHistoryStore
from radar.observability.models import RunRecord
from radar.pipeline import PipelineReport


def _report() -> PipelineReport:
    return PipelineReport(
        n_fetched=5,
        n_dedup=5,
        n_fresh=5,
        n_unseen=5,
        n_scored=5,
        n_above_threshold=1,
        n_drafted=1,
        n_llm_calls=6,
        n_failures=0,
        drafts=[],
    )


def _record(*, minute: int = 0, cost_usd: float = 0.01) -> RunRecord:
    return RunRecord(
        at=datetime(2026, 8, 29, 12, minute, tzinfo=UTC),
        report=_report(),
        usage=LlmUsage(input_tokens=1000, output_tokens=50, cost_usd=cost_usd),
    )


def test_json_run_history_round_trip(tmp_path: Path) -> None:
    store = JsonRunHistoryStore(tmp_path / "run_history.json")
    record = _record()

    store.append(record)

    assert store.recent(1) == [record]


def test_json_run_history_loads_empty_when_missing(tmp_path: Path) -> None:
    store = JsonRunHistoryStore(tmp_path / "missing.json")

    assert store.recent(10) == []


def test_json_run_history_loads_empty_for_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "corrupted.json"
    path.write_text("%%%", encoding="utf-8")
    store = JsonRunHistoryStore(path)

    assert store.recent(10) == []


def test_json_run_history_recent_returns_n_most_recent(tmp_path: Path) -> None:
    store = JsonRunHistoryStore(tmp_path / "run_history.json")
    for minute in range(5):
        store.append(_record(minute=minute))

    recent = store.recent(2)

    assert [r.at.minute for r in recent] == [3, 4]


def test_json_run_history_store_is_bounded(tmp_path: Path) -> None:
    store = JsonRunHistoryStore(tmp_path / "run_history.json", max_records=2)

    for minute in range(3):
        store.append(_record(minute=minute))

    kept = store.recent(10)

    assert [r.at.minute for r in kept] == [1, 2]  # the minute=0 run was purged


def test_in_memory_run_history_store_round_trip() -> None:
    store = InMemoryRunHistoryStore()
    record = _record()

    store.append(record)

    assert store.recent(1) == [record]


def test_in_memory_run_history_store_is_bounded() -> None:
    store = InMemoryRunHistoryStore(max_records=2)

    for minute in range(3):
        store.append(_record(minute=minute))

    assert [r.at.minute for r in store.recent(10)] == [1, 2]
