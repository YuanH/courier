"""Base destination interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from courier.sources.base import Item

if TYPE_CHECKING:
    import httpx

    from courier.config import Destination as DestinationConfig


class Destination(ABC):
    """A destination delivers Items somewhere."""

    @classmethod
    @abstractmethod
    def from_config(cls, cfg: DestinationConfig, client: httpx.Client) -> Destination:
        """Build a destination instance from a config entry and shared client."""
        ...

    @abstractmethod
    def send(self, item: Item, source_name: str) -> None:
        """Deliver an item from the given source."""
        ...