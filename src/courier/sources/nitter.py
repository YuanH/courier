"""Nitter RSS source — fetch tweets via Nitter RSS feeds."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import feedparser
import httpx

from courier.sources.base import Item, Source

_ID_PATTERN = re.compile(r"/status/(\d+)")


def _extract_id(link: str) -> str | None:
    m = _ID_PATTERN.search(link)
    return m.group(1) if m else None


def _extract_text(entry: dict) -> str:
    summary = entry.get("summary", "")
    return summary


class NitterSource(Source):
    def __init__(
        self,
        handle: str,
        display_name: str,
        nitter_instances: list[str],
        client: httpx.Client | None = None,
    ) -> None:
        self._handle = handle
        self._display_name = display_name
        self._instances = nitter_instances
        self._client = client or httpx.Client(timeout=15)

    @property
    def handle(self) -> str:
        return self._handle

    def fetch(self, since_id: str | None) -> list[Item]:
        items: list[Item] = []

        for instance in self._instances:
            url = f"{instance.rstrip('/')}/{self._handle}/rss"
            try:
                r = self._client.get(url)
                r.raise_for_status()
            except httpx.HTTPError:
                continue

            feed = feedparser.parse(r.text)
            for entry in feed.entries:
                link = entry.get("link", "")
                item_id = _extract_id(link)
                if not item_id:
                    continue
                if since_id and item_id <= since_id:
                    continue

                text = _extract_text(entry)
                published = entry.get("published", "")
                media_urls = []
                if "media_content" in entry:
                    for mc in entry.get("media_content", []):
                        url = mc.get("url", "")
                        if url:
                            media_urls.append(url)

                items.append(
                    Item(
                        id=item_id,
                        text=text,
                        url=link,
                        author=self._display_name or self._handle,
                        timestamp=published,
                        media_urls=media_urls,
                    )
                )

            # If we got results from this instance, don't try fallbacks
            if items:
                break

        items.sort(key=lambda i: i.id)
        return items