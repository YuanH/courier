import httpx
import pytest

from courier.config import Destination, Source
from courier.destinations import (
    UnsupportedDestinationType,
    build_destination,
)
from courier.destinations.discord import DiscordWebhookDestination
from courier.sources import SourceContext, UnsupportedSourceType, build_source
from courier.sources.nitter import NitterSource
from courier.sources.youtube import YouTubeSource


def make_ctx() -> SourceContext:
    return SourceContext(
        client=httpx.Client(timeout=5),
        nitter_instances=["https://nitter.net"],
    )


def test_build_source_returns_nitter_for_nitter_type():
    source = build_source(Source(handle="someone", type="nitter"), make_ctx())
    assert isinstance(source, NitterSource)
    assert source.handle == "someone"


def test_build_source_returns_youtube_for_youtube_type():
    source = build_source(
        Source(handle="@mkbhd", type="youtube", channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw"),
        make_ctx(),
    )
    assert isinstance(source, YouTubeSource)
    assert source.handle == "@mkbhd"


def test_build_source_rejects_unknown_type():
    with pytest.raises(UnsupportedSourceType):
        build_source(Source(handle="x", type="reddit"), make_ctx())


def test_build_destination_returns_discord_for_discord_type():
    dest = build_destination(
        Destination(id="futbol", webhook_url="https://discord.invalid/x"),
        httpx.Client(timeout=5),
    )
    assert isinstance(dest, DiscordWebhookDestination)


def test_build_destination_rejects_unknown_type():
    with pytest.raises(UnsupportedDestinationType):
        build_destination(
            Destination(id="x", webhook_url="https://x", type="slack"),
            httpx.Client(timeout=5),
        )
