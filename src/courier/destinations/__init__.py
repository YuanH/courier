"""Destination plugins — push data to external services.

The registry maps a config ``type`` to a concrete :class:`Destination` class,
mirroring the source registry so new delivery targets stay plug-in shaped.
"""

from __future__ import annotations

import httpx

from courier.config import Destination as DestinationConfig
from courier.destinations.base import Destination
from courier.destinations.discord import DiscordWebhookDestination


class UnsupportedDestinationType(ValueError):
    """Raised when a config references a destination type with no class."""


DESTINATION_TYPES: dict[str, type[Destination]] = {
    "discord": DiscordWebhookDestination,
}


def build_destination(cfg: DestinationConfig, client: httpx.Client) -> Destination:
    cls = DESTINATION_TYPES.get(cfg.type)
    if cls is None:
        raise UnsupportedDestinationType(
            f"Unsupported destination type {cfg.type!r} for {cfg.id!r}"
        )
    return cls.from_config(cfg, client)
