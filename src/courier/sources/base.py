"""Base source interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from courier.config import Source as SourceConfig
    from courier.sources import SourceContext


@dataclass
class ProbeResult:
    """One diagnostic attempt against one upstream endpoint.

    Sources that talk to flaky third-party endpoints can report what happened
    at each stage so an operator can tell a dead host from a bot challenge
    from a feed that simply had nothing new.
    """

    endpoint: str
    outcome: str
    detail: str = ""
    status: int | None = None
    bytes: int = 0
    entries: int = 0
    item_ids: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"


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

    def probe(self) -> list[ProbeResult]:
        """Diagnose connectivity without touching dedupe state.

        Sources with several interchangeable upstreams should try every one and
        report each result instead of stopping at the first success. The default
        is an empty list, meaning "this source has nothing to diagnose".
        """
        return []