from pathlib import Path

from composition import build_agent, build_executor, build_radar_pipeline
from settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="test-key-not-a-real-secret",
        feed_urls=["https://example.com/feed"],
        store_dir=tmp_path,
    )


def test_composition_builds_radar_pipeline(tmp_path: Path) -> None:
    run = build_radar_pipeline(_settings(tmp_path))

    assert callable(run)  # wired without crashing (not executed: no network/LLM)


def test_composition_builds_agent(tmp_path: Path) -> None:
    handle = build_agent(_settings(tmp_path))

    assert callable(handle)


def test_composition_builds_executor(tmp_path: Path) -> None:
    run = build_executor(_settings(tmp_path))

    assert callable(run)
