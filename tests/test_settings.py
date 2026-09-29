import subprocess
from pathlib import Path

import pytest

from settings import MissingSettingError, load_settings

REPO = Path(__file__).resolve().parents[1]


def test_load_settings_success() -> None:
    env = {
        "ANTHROPIC_API_KEY": "test-key-not-a-real-secret",
        "FEED_URLS": "https://a.example/feed, https://b.example/feed",
        "STORE_DIR": "/tmp/store",
    }

    settings = load_settings(env)

    assert settings.anthropic_api_key == "test-key-not-a-real-secret"
    assert settings.feed_urls == ["https://a.example/feed", "https://b.example/feed"]
    assert settings.store_dir == Path("/tmp/store")


def test_load_settings_missing_key() -> None:
    env = {"FEED_URLS": "https://a.example/feed"}  # ANTHROPIC_API_KEY absent

    with pytest.raises(MissingSettingError, match="ANTHROPIC_API_KEY"):
        load_settings(env)


def test_env_is_gitignored() -> None:
    lines = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in lines


def test_no_secret_in_repo() -> None:
    marker = "sk-" + "ant-"  # concatenated so the file does not flag itself
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )

    offenders: list[str] = []
    for line in tracked.stdout.splitlines():
        try:
            content = (REPO / line).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if marker in content:
            offenders.append(line)

    assert offenders == [], f"secret potentiel (clé Anthropic) dans : {offenders}"
