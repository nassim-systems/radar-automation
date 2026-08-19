from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

_DEFAULT_STORE_DIR = ".data"


class MissingSettingError(Exception):
    """Levée quand une variable d'environnement requise est absente."""


class Settings(BaseModel):
    anthropic_api_key: str
    feed_urls: list[str]
    store_dir: Path


def load_settings(env: Mapping[str, str]) -> Settings:
    """Charge la configuration depuis un environnement injecté — PUR, fail-fast.

    Les secrets ne proviennent QUE de ``env`` (jamais du code, jamais de git).
    Fonction pure : dépend uniquement de ``env``. Lève ``MissingSettingError``
    dès qu'une variable requise manque.
    """
    api_key = _require(env, "ANTHROPIC_API_KEY")
    feed_urls = [
        url.strip() for url in _require(env, "FEED_URLS").split(",") if url.strip()
    ]
    store_dir = Path(env.get("STORE_DIR", "").strip() or _DEFAULT_STORE_DIR)
    return Settings(
        anthropic_api_key=api_key, feed_urls=feed_urls, store_dir=store_dir
    )


def _require(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise MissingSettingError(
            f"variable d'environnement requise manquante : {key}"
        )
    return value
