from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol


class SeenStore(Protocol):
    def load_seen(self) -> set[str]:
        ...

    def add_seen(self, keys: Iterable[str]) -> None:
        ...


class JsonSeenStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_seen(self) -> set[str]:
        if not self.path.exists():
            return set()

        try:
            content = self.path.read_text(encoding="utf-8")
            data = json.loads(content)
            return set(data) if isinstance(data, list) else set()
        except (OSError, json.JSONDecodeError):
            return set()

    def add_seen(self, keys: Iterable[str]) -> None:
        seen = self.load_seen()
        seen.update(keys)
        content = json.dumps(sorted(seen), ensure_ascii=False)
        self.path.write_text(content, encoding="utf-8")


class InMemorySeenStore:
    """Non-persistent SeenStore (tests, ephemeral runs)."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def load_seen(self) -> set[str]:
        return set(self._seen)

    def add_seen(self, keys: Iterable[str]) -> None:
        self._seen.update(keys)
