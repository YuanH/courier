"""Deduplication state — tracks last-seen IDs per source."""

from __future__ import annotations

import json
from pathlib import Path


class State:
    _data: dict[str, str]  # source_handle -> last_seen_id

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if self._path.exists():
            raw = self._path.read_text()
            self._data = json.loads(raw) if raw.strip() else {}
        else:
            self._data = {}

    def get(self, handle: str) -> str | None:
        return self._data.get(handle)

    def set(self, handle: str, last_id: str) -> None:
        self._data[handle] = last_id

    def save(self) -> None:
        self._path.write_text(json.dumps(self._data, indent=2))