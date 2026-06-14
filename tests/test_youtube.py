import httpx

from courier.sources.youtube import YouTubeSource

CHANNEL_ID = "UC_x5XG1OV2P6uZZ5FSM9Ttw"

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Test Channel</title>
  <entry>
    <id>yt:video:AAA11111111</id>
    <yt:videoId>AAA11111111</yt:videoId>
    <title>Older video</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=AAA11111111"/>
    <published>2026-06-10T10:00:00+00:00</published>
    <media:group>
      <media:thumbnail url="https://i.ytimg.com/vi/AAA11111111/hq.jpg"/>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:BBB22222222</id>
    <yt:videoId>BBB22222222</yt:videoId>
    <title>Newer video</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=BBB22222222"/>
    <published>2026-06-12T15:30:00+00:00</published>
    <media:group>
      <media:thumbnail url="https://i.ytimg.com/vi/BBB22222222/hq.jpg"/>
    </media:group>
  </entry>
</feed>
"""

CHANNEL_PAGE = f'<html><head><meta><script>"channelId":"{CHANNEL_ID}"</script></head></html>'


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.content = text.encode()

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPError(f"status {self.status_code}")


class FakeClient:
    """Routes requests by URL: feed XML for the RSS endpoint, HTML otherwise."""

    def __init__(self, feed: str = FEED, page: str = CHANNEL_PAGE) -> None:
        self.feed = feed
        self.page = page
        self.calls: list[str] = []

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(url)
        if "feeds/videos.xml" in url:
            return FakeResponse(self.feed)
        return FakeResponse(self.page)


def test_fetch_uses_publish_timestamp_as_id_and_sorts_ascending():
    source = YouTubeSource(
        handle="testchannel",
        display_name="Test Channel",
        channel_id=CHANNEL_ID,
        client=FakeClient(),
    )

    items = source.fetch(None)

    assert [item.id for item in items] == [
        "2026-06-10T10:00:00Z",
        "2026-06-12T15:30:00Z",
    ]
    assert items[-1].url == "https://www.youtube.com/watch?v=BBB22222222"
    assert items[-1].raw == {"video_id": "BBB22222222"}
    assert items[-1].author == "Test Channel"


def test_fetch_filters_items_at_or_before_since_id():
    source = YouTubeSource(
        handle="testchannel",
        display_name="Test Channel",
        channel_id=CHANNEL_ID,
        client=FakeClient(),
    )

    items = source.fetch("2026-06-10T10:00:00Z")

    assert [item.id for item in items] == ["2026-06-12T15:30:00Z"]


def test_resolves_channel_id_from_handle_then_fetches_feed():
    client = FakeClient()
    source = YouTubeSource(
        handle="@testchannel",
        display_name="Test Channel",
        client=client,
    )

    items = source.fetch(None)

    assert len(items) == 2
    # First call scrapes the channel page, second hits the resolved RSS feed.
    assert client.calls[0] == "https://www.youtube.com/@testchannel"
    assert f"channel_id={CHANNEL_ID}" in client.calls[1]
    # Resolution is cached: a second fetch does not scrape the page again.
    source.fetch(None)
    assert client.calls.count("https://www.youtube.com/@testchannel") == 1


def test_unresolvable_channel_returns_no_items_without_raising():
    client = FakeClient(page="<html>no id here</html>")
    source = YouTubeSource(handle="@nope", display_name="Nope", client=client)

    assert source.fetch(None) == []
