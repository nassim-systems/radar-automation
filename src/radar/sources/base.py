from typing import Protocol

from radar.domain import RawItem


class Source(Protocol):
    name: str

    def fetch(self) -> list[RawItem]:
        ...
