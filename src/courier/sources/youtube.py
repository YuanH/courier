"""YouTube source — fetch channel uploads via the public RSS feed.

YouTube publishes a per-channel Atom feed at
``https://www.youtube.com/feeds/videos.xml?channel_id=UC...`` with the latest
~15 uploads, no API key required. Video IDs are not ordered, so unlike Nitter
this source uses each video's publish timestamp as the dedupe cursor: ``Item.id``
is the UTC publish time formatted ``YYYY-MM-DDTHH:MM:SSZ``, which sorts
lexicographically in chronological order and round-trips through the engine's
``since_id`` watermark unchanged. The real video ID lives in ``Item.url``.
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

import feedparser
import httpx

from courier.sources.base import Item, Source

if TYPE_CHECKING:
    from courier.config import Source as SourceConfig
    from courier.sources import SourceContext

logger = logging.getLogger("courier.sources.youtube")

_CHANNEL_ID_RE = re.compile(r"(UC[0-9A-Za-z_-]{22})")
_WATCH_ID_RE = re.compile(r"[?&]v=([0-9A-Za-z_-]{11})")
_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


def _channel_page_url(candidate: str) -> str:
    """Map a handle/URL hint to a channel page we can scrape for its UC id."""
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    if candidate.startswith("@"):
        return f"https://www.youtube.com/{candidate}"
    return f"https://www.youtube.com/@{candidate}"


def _video_id(entry, link: str) -> str:
    video_id = entry.get("yt_videoid", "")
    if video_id:
        return video_id
    m = _WATCH_ID_RE.search(link)
    return m.group(1) if m else ""


def _thumbnails(entry) -> list[str]:
    urls: list[str] = []
    for thumb in entry.get("media_thumbnail", []) or []:
        url = thumb.get("url", "")
        if url:
            urls.append(url)
    return urls


class YouTubeSource(Source):
    def __init__(
        self,
        handle: str,
        display_name: str,
        channel_id: str = "",
        url: str = "",
        client: httpx.Client | None = None,
    ) -> None:
        self._handle = handle
        self._display_name = display_name or handle
        self._channel_id = channel_id
        self._url = url
        self._client = client or httpx.Client(timeout=15)
        # Cached UC id once resolved. Seeded if the config already gave us one.
        self._resolved_id: str | None = None
        if channel_id:
            m = _CHANNEL_ID_RE.fullmatch(channel_id) or _CHANNEL_ID_RE.search(channel_id)
            if m:
                self._resolved_id = m.group(1)

    @classmethod
    def from_config(cls, cfg: SourceConfig, ctx: SourceContext) -> YouTubeSource:
        return cls(
            handle=cfg.handle,
            display_name=cfg.display_name,
            channel_id=cfg.channel_id,
            url=cfg.url,
            client=ctx.client,
        )

    @property
    def handle(self) -> str:
        return self._handle

    def _resolve_channel_id(self) -> str | None:
        """Resolve and cache the UC channel id from config hints.

        Tries, in order: an explicit/embedded UC id, then scraping the channel
        page referenced by ``url`` or ``handle``. Cached so we scrape at most
        once per process; a failure leaves the cache empty so the next poll
        retries.
        """
        if self._resolved_id:
            return self._resolved_id

        for candidate in (self._url, self._handle):
            if not candidate:
                continue
            m = _CHANNEL_ID_RE.search(candidate)
            if m:
                self._resolved_id = m.group(1)
                return self._resolved_id

        candidate = self._url or self._handle
        if not candidate:
            return None

        page_url = _channel_page_url(candidate)
        try:
            r = self._client.get(
                page_url,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "Failed to resolve channel id for %s from %s: %s",
                self._handle,
                page_url,
                exc,
            )
            return None

        m = _CHANNEL_ID_RE.search(r.text)
        if not m:
            logger.warning(
                "Could not find channel id for %s in %s", self._handle, page_url
            )
            return None

        self._resolved_id = m.group(1)
        logger.info("Resolved %s to channel id %s", self._handle, self._resolved_id)
        return self._resolved_id

    def fetch(self, since_id: str | None) -> list[Item]:
        channel_id = self._resolve_channel_id()
        if not channel_id:
            return []

        url = _FEED_URL.format(channel_id=channel_id)
        try:
            r = self._client.get(
                url,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch %s from %s: %s", self._handle, url, exc)
            return []

        body = r.text
        if not body.strip():
            logger.warning(
                "Empty feed body for %s from %s status=%s bytes=%d",
                self._handle,
                url,
                r.status_code,
                len(r.content),
            )
            return []

        feed = feedparser.parse(body)
        if feed.bozo:
            logger.warning(
                "Feed parse error for %s from %s bytes=%d error=%s",
                self._handle,
                url,
                len(r.content),
                getattr(feed, "bozo_exception", "unknown"),
            )
            return []

        if not feed.entries:
            logger.warning(
                "No feed entries for %s from %s status=%s bytes=%d",
                self._handle,
                url,
                r.status_code,
                len(r.content),
            )
            return []

        logger.info(
            "Fetched %s from %s: status=%s bytes=%d entries=%d",
            self._handle,
            url,
            r.status_code,
            len(r.content),
            len(feed.entries),
        )

        items: list[Item] = []
        for entry in feed.entries:
            published = entry.get("published_parsed")
            if not published:
                continue
            cursor = time.strftime("%Y-%m-%dT%H:%M:%SZ", published)
            if since_id and cursor <= since_id:
                continue

            link = entry.get("link", "")
            items.append(
                Item(
                    id=cursor,
                    text=entry.get("title", ""),
                    url=link,
                    author=self._display_name,
                    timestamp=entry.get("published", ""),
                    media_urls=_thumbnails(entry),
                    raw={"video_id": _video_id(entry, link)},
                )
            )

        items.sort(key=lambda i: i.id)
        return items
