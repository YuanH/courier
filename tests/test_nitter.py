from typing import cast

import httpx

from courier.sources.nitter import _BROWSER_USER_AGENT, _RSS_USER_AGENT, NitterSource


VALID_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>FabrizioRomano / Twitter</title>
    <item>
      <title>New transfer news</title>
      <link>https://nitter.net/FabrizioRomano/status/2062170298984652870#m</link>
      <pubDate>Wed, 03 Jun 2026 13:51:27 GMT</pubDate>
      <description>New transfer news</description>
    </item>
  </channel>
</rss>
"""

# A bare "&" in a tweet makes feedparser flag the feed as bozo even though the
# entries parse fine — dropping those used to lose the whole instance.
BOZO_FEED_WITH_ENTRY = VALID_FEED.replace(
    "New transfer news", "Man Utd & Chelsea agree deal", 1
)

BOT_CHALLENGE = "<!doctype html><html><title>Making sure you're not a bot!</title></html>"


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.content = text.encode() if isinstance(text, str) else text
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": "application/rss+xml"}


class FakeClient:
    """Serves canned responses, either in order or keyed by (url, user-agent)."""

    def __init__(self, responses=None, by_key=None):
        self.responses = list(responses or [])
        self.by_key = by_key or {}
        self.calls = []

    def get(self, url, **kwargs):
        user_agent = kwargs["headers"]["User-Agent"]
        self.calls.append((url, kwargs))
        if self.by_key:
            return self.by_key[(url, user_agent)]
        return self.responses.pop(0)


def make_source(instances, client):
    return NitterSource(
        "FabrizioRomano", "Fabrizio Romano", instances, cast(httpx.Client, client)
    )


def test_fetch_uses_browser_identity_and_follows_redirects():
    client = FakeClient([FakeResponse(VALID_FEED)])
    items = make_source(["https://nitter.net"], client).fetch(None)

    assert [i.id for i in items] == ["2062170298984652870"]
    _, kwargs = client.calls[0]
    assert kwargs["follow_redirects"] is True
    assert kwargs["headers"]["User-Agent"] == _BROWSER_USER_AGENT


def test_fetch_retries_same_instance_with_rss_identity_on_403():
    client = FakeClient([FakeResponse("nope", status_code=403), FakeResponse(VALID_FEED)])
    items = make_source(["https://xcancel.com"], client).fetch(None)

    assert [i.id for i in items] == ["2062170298984652870"]
    assert [c[1]["headers"]["User-Agent"] for c in client.calls] == [
        _BROWSER_USER_AGENT,
        _RSS_USER_AGENT,
    ]


def test_fetch_retries_with_rss_identity_on_bot_challenge():
    client = FakeClient([FakeResponse(BOT_CHALLENGE), FakeResponse(VALID_FEED)])
    items = make_source(["https://xcancel.com"], client).fetch(None)

    assert [i.id for i in items] == ["2062170298984652870"]
    assert len(client.calls) == 2


def test_fetch_does_not_retry_identity_on_server_error():
    client = FakeClient([FakeResponse("boom", status_code=503), FakeResponse(VALID_FEED)])
    items = make_source(["https://nitter.net", "https://xcancel.com"], client).fetch(None)

    # One attempt at the dead instance, then straight on to the next host.
    assert [c[0] for c in client.calls] == [
        "https://nitter.net/FabrizioRomano/rss",
        "https://xcancel.com/FabrizioRomano/rss",
    ]
    assert [i.id for i in items] == ["2062170298984652870"]


def test_fetch_accepts_feed_with_leading_whitespace_and_bom():
    client = FakeClient([FakeResponse("﻿  \n" + VALID_FEED)])
    items = make_source(["https://xcancel.com"], client).fetch(None)

    assert [i.id for i in items] == ["2062170298984652870"]


def test_fetch_keeps_entries_from_a_feed_flagged_bozo():
    client = FakeClient([FakeResponse(BOZO_FEED_WITH_ENTRY)])
    items = make_source(["https://nitter.net"], client).fetch(None)

    assert [i.id for i in items] == ["2062170298984652870"]


def test_fetch_falls_back_when_an_instance_serves_html():
    client = FakeClient(
        [FakeResponse(BOT_CHALLENGE), FakeResponse(BOT_CHALLENGE), FakeResponse(VALID_FEED)]
    )
    items = make_source(
        ["https://nitter.privacyredirect.com", "https://nitter.net"], client
    ).fetch(None)

    assert [i.id for i in items] == ["2062170298984652870"]
    assert len(client.calls) == 3


def test_fetch_falls_back_when_an_instance_serves_an_empty_feed():
    empty = VALID_FEED.replace(VALID_FEED[VALID_FEED.index("<item>") : VALID_FEED.index("</item>") + 7], "")
    client = FakeClient([FakeResponse(empty), FakeResponse(VALID_FEED)])
    items = make_source(["https://nitter.net", "https://xcancel.com"], client).fetch(None)

    assert [i.id for i in items] == ["2062170298984652870"]


def test_fetch_filters_by_watermark_numerically():
    client = FakeClient([FakeResponse(VALID_FEED)])
    items = make_source(["https://nitter.net"], client).fetch("2062170298984652870")

    assert items == []


def test_fetch_refuses_to_replay_history_on_a_corrupt_watermark():
    client = FakeClient([FakeResponse(VALID_FEED)])
    items = make_source(["https://nitter.net"], client).fetch("2026-08-21T10:00:00Z")

    assert items == []
    assert client.calls == []


def test_fetch_returns_nothing_when_every_instance_fails():
    client = FakeClient([FakeResponse("", status_code=404)] * 4)
    items = make_source(["https://nitter.net", "https://xcancel.com"], client).fetch(None)

    assert items == []
    assert len(client.calls) == 4


def test_probe_reports_every_instance_without_stopping_early():
    client = FakeClient(
        by_key={
            ("https://nitter.net/FabrizioRomano/rss", _BROWSER_USER_AGENT): FakeResponse(""),
            ("https://xcancel.com/FabrizioRomano/rss", _BROWSER_USER_AGENT): FakeResponse(
                VALID_FEED
            ),
        }
    )
    results = make_source(["https://nitter.net", "https://xcancel.com"], client).probe()

    assert [(r.outcome, r.ok) for r in results] == [("empty-body", False), ("ok", True)]
    assert results[1].item_ids == ["2062170298984652870"]


def test_media_urls_do_not_clobber_the_feed_url():
    feed = VALID_FEED.replace(
        "</item>",
        '<media:content url="https://nitter.net/pic/media.jpg" '
        'xmlns:media="http://search.yahoo.com/mrss/"/></item>',
    )
    client = FakeClient([FakeResponse(feed)])
    items = make_source(["https://nitter.net"], client).fetch(None)

    assert items[0].url == "https://nitter.net/FabrizioRomano/status/2062170298984652870#m"
    assert items[0].media_urls == ["https://nitter.net/pic/media.jpg"]


def test_base_url_provider_gets_the_nitter_feed_layout():
    client = FakeClient([FakeResponse(VALID_FEED)])
    make_source(["https://nitter.poast.org/"], client).fetch(None)

    assert client.calls[0][0] == "https://nitter.poast.org/FabrizioRomano/rss"


def test_template_provider_places_the_handle_itself():
    client = FakeClient([FakeResponse(VALID_FEED)])
    make_source(["https://rsshub.example.com/twitter/user/{handle}"], client).fetch(None)

    assert client.calls[0][0] == "https://rsshub.example.com/twitter/user/FabrizioRomano"


def test_browser_identity_sends_a_full_browser_header_set():
    client = FakeClient([FakeResponse(VALID_FEED)])
    make_source(["https://nitter.net"], client).fetch(None)

    headers = client.calls[0][1]["headers"]
    assert headers["User-Agent"] == _BROWSER_USER_AGENT
    assert headers["Accept-Language"].startswith("en-US")
    assert headers["Sec-Fetch-Mode"] == "navigate"


def test_valid_rss_carrying_only_an_interstitial_is_not_a_success():
    """XCancel's whitelist page parses as RSS but links to no tweet."""
    interstitial = VALID_FEED.replace(
        "https://nitter.net/FabrizioRomano/status/2062170298984652870#m",
        "https://xcancel.com/about/whitelist",
    )
    client = FakeClient([FakeResponse(interstitial), FakeResponse(VALID_FEED)])
    source = make_source(["https://xcancel.com", "https://nitter.poast.org"], client)

    items = source.fetch(None)

    assert [i.id for i in items] == ["2062170298984652870"]
    assert client.calls[-1][0] == "https://nitter.poast.org/FabrizioRomano/rss"
