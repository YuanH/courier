"""Base source interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from courier.config import Source as SourceConfig
    from courier.sources import SourceContext


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

    @classmethod
    @abstractmethod
    def from_config(cls, cfg: SourceConfig, ctx: SourceContext) -> Source:
        """Build a source instance from a config entry and shared build context."""
        ...

    @abstractmethod
    def fetch(self, since_id: str | None) -> list[Item]:
        """Fetch items newer than since_id (or all recent if None).

        Items must be returned in ascending order; the engine treats the last
        item's ``id`` as the new watermark and passes it back as ``since_id``.
        The ``id`` is therefore an opaque, source-defined cursor token — a
        numeric status ID for Nitter, a publish timestamp for YouTube.
        """
        ...

    @property
    @abstractmethod
    def handle(self) -> str:
        """Unique handle/name for this source."""
        ...