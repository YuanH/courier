"""Discord webhook destination — send items as rich embeds."""

from __future__ import annotations

import time

import httpx

from courier.destinations.base import Destination
from courier.sources.base import Item

_TWITTER_BLUE = 0x1DA1F2


def _build_embed(item: Item, source_name: str) -> dict:
    embed: dict = {
        "description": item.text[:2000],
        "url": item.url,
        "color": _TWITTER_BLUE,
        "footer": {"text": f"🐦 {source_name}"},
    }
    if item.author:
        embed["author"] = {"name": item.author}
    if item.timestamp:
        embed["timestamp"] = item.timestamp
    # First media as image
    for media in item.media_urls:
        embed["image"] = {"url": media}
        break
    return embed


class DiscordWebhookDestination(Destination):
    def __init__(
        self,
        dest_id: str,
        webhook_url: str,
        display_name: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._id = dest_id
        self._webhook_url = webhook_url
        self._display_name = display_name
        self._client = client or httpx.Client(timeout=10)

    def send(self, item: Item, source_name: str) -> None:
        embed = _build_embed(item, source_name)
        payload = {
            "username": source_name,
            "embeds": [embed],
        }

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