"""Discord webhook destination — send items as fxtwitter links."""

from __future__ import annotations

import re
import time

import httpx

from courier.destinations.base import Destination
from courier.sources.base import Item

_STATUS_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:x|twitter|nitter|xcancel|fxtwitter)\.\w+/(?P<handle>[^/]+)/status/(?P<status_id>\d+)"
)


def _fxtwitter_url(item: Item) -> str:
    match = _STATUS_URL_RE.search(item.url)
    if not match:
        return item.url
    return f"https://fxtwitter.com/{match.group('handle')}/status/{match.group('status_id')}?s=20"


def _build_payload(item: Item, source_name: str) -> dict:
    return {
        "username": source_name,
        "content": _fxtwitter_url(item),
    }


class DiscordWebhookDestination(Destination):
    def __init__(
        self,
        webhook_url: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._client = client or httpx.Client(timeout=10)

    def send(self, item: Item, source_name: str) -> None:
        payload = _build_payload(item, source_name)

        for attempt in range(3):
            try:
                r = self._client.post(self._webhook_url, json=payload)
                if r.status_code == 204:
                    return
                if r.status_code in (429, 409):
                    retry_after = r.json().get("retry_after", 5)
                    time.sleep(retry_after)
                    continue
                r.raise_for_status()
                return
            except httpx.HTTPError:
                if attempt < 2:
                    time.sleep(2**attempt)
                else:
                    raise