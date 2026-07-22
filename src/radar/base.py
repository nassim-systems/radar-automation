from abc import ABC, abstractmethod
from typing import Iterable

from radar.domain import RawItem


class SourceBase(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def fetch(self) -> list[RawItem]:
        raise NotImplementedError
