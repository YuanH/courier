"""Nitter RSS source — fetch tweets via Nitter RSS feeds.

The surviving Nitter instances are fragile: hosts disappear, RSS endpoints get
put behind bot challenges, and a feed that works for one User-Agent is refused
for another. The fetch path therefore treats every instance as untrusted,
records why each attempt failed, and only stops once one of them actually
yields tweet links.
"""

from __future__ import annotations

import codecs
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import feedparser
import httpx

from courier.sources.base import Item, ProbeResult, Source

if TYPE_CHECKING:
    from courier.config import Source as SourceConfig
    from courier.sources import SourceContext

logger = logging.getLogger("courier.sources.nitter")

_ID_PATTERN = re.compile(r"/status/(\d+)")

_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)
_RSS_USER_AGENT = "Feedly/1.0 (+https://feedly.com/i/feed)"

# Instances disagree about which identity they accept: some refuse anything
# that does not look like a browser, and some refuse browsers on their
# RSS-only hosts. Rather than hard-coding a guess per domain, try the browser
# identity first and fall back to the feed-reader one when a response looks
# like a refusal rather than an outage.
_USER_AGENTS = (_BROWSER_USER_AGENT, _RSS_USER_AGENT)

_ACCEPT = "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"

# Outcomes worth re-trying under the other identity; anything else (a dead
# host, a 5xx, an empty body) will fail the same way whoever is asking.
_RETRY_WITH_OTHER_UA = {"http-error", "bot-challenge"}


def _strip_preamble(raw: bytes) -> bytes:
    """Drop byte-order marks and leading whitespace before the XML declaration.

    ``rss.xcancel.com`` pads feeds with whitespace, and some instances emit a
    UTF-8 BOM. Either one makes an otherwise valid feed fail to parse, and a
    BOM survives ``str.lstrip()``, so normalise on bytes before parsing.
    """
    previous = None
    while raw != previous:
        previous = raw
        raw = raw.lstrip()
        if raw.startswith(codecs.BOM_UTF8):
            raw = raw[len(codecs.BOM_UTF8) :]
    return raw


def _looks_like_html(body: bytes) -> bool:
    prefix = body[:500].lower()
    return prefix.startswith(b"<!doctype html") or b"<html" in prefix


def _extract_id(link: str) -> str | None:
    m = _ID_PATTERN.search(link)
    return m.group(1) if m else None


@dataclass
class _Attempt:
    """A probe result plus the parsed entries, when the attempt succeeded."""

    result: ProbeResult
    entries: list


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
        watermark = self._watermark(since_id)
        if since_id is not None and watermark is None:
            return []

        results: list[ProbeResult] = []
        for instance in self._instances:
            attempt = self._fetch_instance(instance, results)
            if attempt is None:
                continue

            logger.info(
                "Fetched %s from %s: status=%s bytes=%d entries=%d",
                self._handle,
                attempt.result.endpoint,
                attempt.result.status,
                attempt.result.bytes,
                attempt.result.entries,
            )
            return self._items_from(attempt.entries, watermark)

        logger.error(
            "No Nitter instance returned a usable feed for %s — tried %s",
            self._handle,
            "; ".join(self._summarize(r) for r in results) or "<no instances configured>",
        )
        return []

    def probe(self) -> list[ProbeResult]:
        """Try every instance and report each result, without stopping early."""
        results: list[ProbeResult] = []
        for instance in self._instances:
            self._fetch_instance(instance, results)
        return results

    def _fetch_instance(
        self, instance: str, results: list[ProbeResult]
    ) -> _Attempt | None:
        """Try one instance under each identity; return the first usable feed."""
        url = f"{instance.rstrip('/')}/{self._handle}/rss"

        for user_agent in _USER_AGENTS:
            attempt = self._request(url, user_agent)
            results.append(attempt.result)
            if attempt.result.ok:
                return attempt
            if attempt.result.outcome not in _RETRY_WITH_OTHER_UA:
                return None
        return None

    def _request(self, url: str, user_agent: str) -> _Attempt:
        headers = {"User-Agent": user_agent, "Accept": _ACCEPT}

        def failure(outcome: str, detail: str, **kw) -> _Attempt:
            # A single failed attempt is routine in a fallback chain, so log it
            # at INFO; the aggregate ERROR below fires only if nothing worked.
            logger.info(
                "Nitter attempt failed for %s at %s (%s): %s — %s",
                self._handle,
                url,
                user_agent.split("/")[0],
                outcome,
                detail,
            )
            return _Attempt(
                ProbeResult(endpoint=url, outcome=outcome, detail=detail, **kw), []
            )

        try:
            r = self._client.get(url, headers=headers, follow_redirects=True)
        except httpx.HTTPError as exc:
            return failure("unreachable", f"{type(exc).__name__}: {exc}")

        status = r.status_code
        size = len(r.content)

        # Inspect the status directly instead of raising: a 4xx usually means
        # "not with that User-Agent" and is worth another try, while a 5xx
        # means the instance itself is unwell.
        if status >= 500:
            return failure("server-error", f"HTTP {status}", status=status, bytes=size)
        if status >= 400:
            return failure("http-error", f"HTTP {status}", status=status, bytes=size)

        body = _strip_preamble(r.content)
        if not body:
            return failure("empty-body", "no content", status=status, bytes=size)
        if _looks_like_html(body):
            return failure(
                "bot-challenge", "HTML page instead of RSS", status=status, bytes=size
            )

        feed = feedparser.parse(body)
        entries = list(feed.entries)
        bozo_detail = str(getattr(feed, "bozo_exception", "") or "")

        if not entries:
            outcome = "unparseable" if feed.bozo else "no-entries"
            return failure(
                outcome, bozo_detail or "feed had no items", status=status, bytes=size
            )

        item_ids = [
            item_id
            for item_id in (_extract_id(e.get("link", "")) for e in entries)
            if item_id
        ]
        if not item_ids:
            return failure(
                "no-status-links",
                f"{len(entries)} entries, none linking to a tweet",
                status=status,
                bytes=size,
                entries=len(entries),
            )

        if feed.bozo:
            # A stray "&" in a tweet or an undeclared namespace prefix marks an
            # otherwise usable feed as bozo. Dropping it here used to lose every
            # tweet from that instance, so parse what came through and say so.
            logger.warning(
                "Tolerating RSS parse error for %s from %s: %s",
                self._handle,
                url,
                bozo_detail or "unknown",
            )

        return _Attempt(
            ProbeResult(
                endpoint=url,
                outcome="ok",
                detail=bozo_detail,
                status=status,
                bytes=size,
                entries=len(entries),
                item_ids=item_ids,
            ),
            entries,
        )

    def _watermark(self, since_id: str | None) -> int | None:
        if since_id is None:
            return None
        try:
            return int(since_id)
        except ValueError:
            logger.error(
                "Ignoring poll for %s: stored watermark %r is not a numeric status ID. "
                "Fix or remove that entry in the state file to resume.",
                self._handle,
                since_id,
            )
            return None

    def _items_from(self, entries: list, watermark: int | None) -> list[Item]:
        items: list[Item] = []
        for entry in entries:
            link = entry.get("link", "")
            item_id = _extract_id(link)
            if not item_id:
                continue
            if watermark is not None and int(item_id) <= watermark:
                continue

            media_urls = []
            for mc in entry.get("media_content", []) or []:
                media_url = mc.get("url", "")
                if media_url:
                    media_urls.append(media_url)

            items.append(
                Item(
                    id=item_id,
                    text=entry.get("summary", ""),
                    url=link,
                    author=self._display_name or self._handle,
                    timestamp=entry.get("published", ""),
                    media_urls=media_urls,
                )
            )

        items.sort(key=lambda i: int(i.id))
        return items

    @staticmethod
    def _summarize(result: ProbeResult) -> str:
        return f"{result.endpoint} -> {result.outcome} ({result.detail})"
