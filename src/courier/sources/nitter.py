"""Nitter RSS source — fetch tweets via Nitter RSS feeds."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import feedparser
import httpx

from courier.sources.base import Item, Source

if TYPE_CHECKING:
    from courier.config import Source as SourceConfig
    from courier.sources import SourceContext

logger = logging.getLogger("courier.sources.nitter")

_ID_PATTERN = re.compile(r"/status/(\d+)")
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)
_RSS_USER_AGENT = "Feedly/1.0"


def _headers_for_instance(instance: str) -> dict[str, str]:
    """Use an RSS-reader identity for xcancel's RSS-only endpoint.

    xcancel redirects feeds to rss.xcancel.com, which deliberately returns a
    400 page to ordinary browser clients. Nitter instances continue to get the
    browser-like user agent they historically required.
    """
    if "xcancel.com" in instance.lower():
        return {"User-Agent": _RSS_USER_AGENT}
    return {"User-Agent": _USER_AGENT}


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

    @classmethod
    def from_config(cls, cfg: SourceConfig, ctx: SourceContext) -> NitterSource:
        return cls(
            handle=cfg.handle,
            display_name=cfg.display_name or cfg.handle,
            nitter_instances=ctx.nitter_instances,
            client=ctx.client,
        )

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
                    headers=_headers_for_instance(instance),
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

            # rss.xcancel.com prefixes feeds with spaces before the XML
            # declaration; strict feedparser marks that otherwise-valid feed
            # as bozo. Preserve validation for all other providers.
            feed_body = body.lstrip() if "xcancel.com" in instance.lower() else body
            feed = feedparser.parse(feed_body)
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
