from courier.destinations.discord import _build_payload
from courier.sources.base import Item


def test_discord_payload_uses_fxtwitter_link_as_content():
    item = Item(
        id="2062000574208307702",
        text="This text should not be the primary Discord message",
        url="https://nitter.net/RealXavier011/status/2062000574208307702#m",
        author="RealXavier011",
    )

    payload = _build_payload(item, "RealXavier011")

    assert payload == {
        "username": "RealXavier011",
        "content": "https://fxtwitter.com/RealXavier011/status/2062000574208307702?s=20",
    }


def test_discord_payload_preserves_already_fxtwitter_link():
    item = Item(
        id="2062000574208307702",
        text="test",
        url="https://fxtwitter.com/RealXavier011/status/2062000574208307702?s=20",
        author="RealXavier011",
    )

    payload = _build_payload(item, "RealXavier011")

    assert payload["content"] == "https://fxtwitter.com/RealXavier011/status/2062000574208307702?s=20"
