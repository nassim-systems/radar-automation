import importlib.util
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from radar.pipeline import PipelineReport
from settings import Settings

REPO = Path(__file__).resolve().parents[1]
_RUN_RADAR = REPO / "scripts" / "run_radar.py"


def _load_main() -> Callable[..., int]:
    spec = importlib.util.spec_from_file_location("run_radar", _RUN_RADAR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


_main = _load_main()


def _fake_report() -> PipelineReport:
    return PipelineReport(
        n_fetched=3,
        n_dedup=3,
        n_fresh=2,
        n_unseen=2,
        n_scored=2,
        n_drafted=0,
        n_llm_calls=2,
        n_failures=0,
        drafts=[],
    )


def test_entrypoint_runs_with_fake_pipeline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _fake_report()

    def _fake_build(settings: Settings) -> Callable[[], PipelineReport]:
        return lambda: report

    env = {"ANTHROPIC_API_KEY": "test-key", "FEED_URLS": "https://x.example/feed"}
    code = _main(env, build=_fake_build)

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n_fetched"] == report.n_fetched
    assert payload["n_drafted"] == report.n_drafted


def test_entrypoint_exit_code_on_missing_config(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _never_build(settings: Settings) -> Callable[[], PipelineReport]:
        raise AssertionError("build ne doit pas être atteint si la config manque")

    code = _main({"FEED_URLS": "https://x.example/feed"}, build=_never_build)

    assert code != 0
    assert "Configuration manquante" in capsys.readouterr().err


def test_scheduling_is_documented() -> None:
    doc = (REPO / "docs" / "ordonnancement.md").read_text(encoding="utf-8").lower()

    assert "cron" in doc
    assert "task scheduler" in doc or "schtasks" in doc
