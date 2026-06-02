"""Base destination interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from courier.sources.base import Item


class Destination(ABC):
    """A destination delivers Items somewhere."""

    @abstractmethod
    def send(self, item: Item, source_name: str) -> None:
        """Deliver an item from the given source."""
        ...