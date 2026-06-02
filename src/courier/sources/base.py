"""Base source interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Item:
    id: str
    text: str
    url: str
    author: str = ""
    timestamp: str = ""
    media_urls: list[str] = field(default_factory=list)
    raw: dict | None = None


class Source(ABC):
    """A source polls external data and yields Items."""

    @abstractmethod
    def fetch(self, since_id: str | None) -> list[Item]:
        """Fetch items newer than since_id (or all recent if None)."""
        ...

    @property
    @abstractmethod
    def handle(self) -> str:
        """Unique handle/name for this source."""
        ...