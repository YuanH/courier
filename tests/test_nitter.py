from typing import cast

import httpx

from courier.sources.nitter import NitterSource


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

MALFORMED_FEED_WITH_ENTRY = """  <?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Malformed but parseable</title>
      <link>https://xcancel.com/FabrizioRomano/status/2062170298984652870#m</link>
    </item>
  </channel>
</rss>
"""


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, url: str = "https://nitter.net/FabrizioRomano/rss"):
        self.text = text
        self.content = text.encode()
        self.status_code = status_code
        self.url = url
        self.headers = {"content-type": "application/rss+xml"}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", str(self.url))
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("bad status", request=request, response=response)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_nitter_fetch_uses_browser_headers_and_redirects():
    client = FakeClient([FakeResponse(VALID_FEED)])
    source = NitterSource("FabrizioRomano", "Fabrizio Romano", ["https://nitter.net"], cast(httpx.Client, client))

    items = source.fetch(None)

    assert len(items) == 1
    _, kwargs = client.calls[0]
    assert kwargs["follow_redirects"] is True
    assert "Mozilla/5.0" in kwargs["headers"]["User-Agent"]


def test_nitter_fetch_rejects_bozo_feed_even_if_entries_parse():
    client = FakeClient([FakeResponse(MALFORMED_FEED_WITH_ENTRY)])
    source = NitterSource("FabrizioRomano", "Fabrizio Romano", ["https://xcancel.com"], cast(httpx.Client, client))

    items = source.fetch(None)

    assert items == []


def test_nitter_fetch_skips_html_bot_check_and_uses_fallback():
    client = FakeClient([
        FakeResponse("<!doctype html><html><title>Making sure you're not a bot!</title></html>"),
        FakeResponse(VALID_FEED, url="https://nitter.net/FabrizioRomano/rss"),
    ])
    source = NitterSource(
        "FabrizioRomano",
        "Fabrizio Romano",
        ["https://nitter.privacyredirect.com", "https://nitter.net"],
        cast(httpx.Client, client),
    )

    items = source.fetch(None)

    assert [item.id for item in items] == ["2062170298984652870"]
    assert len(client.calls) == 2
