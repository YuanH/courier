"""Source plugins — fetch data from external services.

The registry maps a config ``type`` to a concrete :class:`Source` class so the
engine can build sources polymorphically instead of hard-coding each one.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from courier.config import Source as SourceConfig
from courier.sources.base import Source
from courier.sources.nitter import NitterSource
from courier.sources.youtube import YouTubeSource


@dataclass
class SourceContext:
    """Shared dependencies handed to every source at build time."""

    client: httpx.Client
    nitter_instances: list[str]


class UnsupportedSourceType(ValueError):
    """Raised when a config references a source type with no registered class."""


SOURCE_TYPES: dict[str, type[Source]] = {
    "nitter": NitterSource,
    "youtube": YouTubeSource,
}


def build_source(cfg: SourceConfig, ctx: SourceContext) -> Source:
    cls = SOURCE_TYPES.get(cfg.type)
    if cls is None:
        raise UnsupportedSourceType(
            f"Unsupported source type {cfg.type!r} for {cfg.handle!r}"
        )
    return cls.from_config(cfg, ctx)
