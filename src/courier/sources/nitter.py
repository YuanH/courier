"""Nitter RSS source — fetch tweets via Nitter RSS feeds."""

from __future__ import annotations

import logging
import re

import feedparser
import httpx

from courier.sources.base import Item, Source

logger = logging.getLogger("courier.sources.nitter")

_ID_PATTERN = re.compile(r"/status/(\d+)")
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


def _extract_id(link: str) -> str | None:
    m = _ID_PATTERN.search(link)
    return m.group(1) if m else None


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
                r = self._client.get(
                    url,
                    headers={"User-Agent": _USER_AGENT},
                    follow_redirects=True,
                )
                r.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch %s from %s: %s", self._handle, url, exc)
                continue

            body = r.text
            if not body.strip():
                logger.warning(
                    "Empty RSS body for %s from %s status=%s bytes=%d",
                    self._handle,
                    url,
                    r.status_code,
                    len(r.content),
                )
                continue

            body_prefix = body.lstrip()[:500].lower()
            if body_prefix.startswith("<!doctype html") or "<html" in body_prefix:
                logger.warning(
                    "Non-RSS HTML response for %s from %s status=%s bytes=%d",
                    self._handle,
                    url,
                    r.status_code,
                    len(r.content),
                )
                continue

            feed = feedparser.parse(body)
            if feed.bozo:
                logger.warning(
                    "RSS parse error for %s from %s bytes=%d error=%s",
                    self._handle,
                    url,
                    len(r.content),
                    getattr(feed, "bozo_exception", "unknown"),
                )
                continue

            if not feed.entries:
                logger.warning(
                    "No RSS entries for %s from %s status=%s bytes=%d",
                    self._handle,
                    url,
                    r.status_code,
                    len(r.content),
                )
                continue

            logger.info(
                "Fetched %s from %s: status=%s bytes=%d entries=%d",
                self._handle,
                url,
                r.status_code,
                len(r.content),
                len(feed.entries),
            )

            for entry in feed.entries:
                link = entry.get("link", "")
                item_id = _extract_id(link)
                if not item_id:
                    continue
                if since_id and int(item_id) <= int(since_id):
                    continue

                text = entry.get("summary", "")
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

            # If we got a valid feed from this instance, don't try fallbacks.
            break

        items.sort(key=lambda i: int(i.id))
        return items
