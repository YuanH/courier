from typing import cast

from courier.config import Config, Destination, NitterSettings, Route, Settings, Source
from courier.destinations.discord import DiscordWebhookDestination
from courier.engine import Engine
from courier.sources.base import Item
from courier.sources.nitter import NitterSource


class FakeSource:
    def __init__(self, items):
        self.items = items
        self.fetch_calls = []

    def fetch(self, since_id):
        self.fetch_calls.append(since_id)
        return self.items


class FakeDestination:
    def __init__(self):
        self.sent = []

    def send(self, item, handle):
        self.sent.append((item.id, handle))


def make_engine(tmp_path):
    cfg = Config(
        settings=Settings(poll_interval_minutes=5, dedup_persistence=str(tmp_path / "state.json")),
        nitter_instances=NitterSettings(primary="https://nitter.net", fallback="https://xcancel.com"),
        sources=[Source(handle="FabrizioRomano", display_name="Fabrizio Romano")],
        destinations=[Destination(id="futbol", webhook_url="https://discord.invalid/webhook")],
        routes=[Route(source="FabrizioRomano", destinations=["futbol"])],
    )
    return Engine(cfg)


def test_process_source_bootstraps_first_successful_fetch_without_sending(tmp_path):
    engine = make_engine(tmp_path)
    source = FakeSource([
        Item(id="2062170298984652870", text="older", url="https://nitter.net/FabrizioRomano/status/2062170298984652870#m"),
        Item(id="2062187928755867988", text="newest", url="https://nitter.net/FabrizioRomano/status/2062187928755867988#m"),
    ])
    dest = FakeDestination()
    engine._sources = {"FabrizioRomano": cast(NitterSource, source)}
    engine._destinations = {"futbol": cast(DiscordWebhookDestination, dest)}

    engine._process_source("FabrizioRomano", cast(NitterSource, source))

    assert dest.sent == []
    assert (tmp_path / "state.json").read_text() == '{\n  "FabrizioRomano": "2062187928755867988"\n}'
    assert source.fetch_calls == [None]


def test_process_source_sends_items_when_state_already_exists(tmp_path):
    engine = make_engine(tmp_path)
    engine._state.set("FabrizioRomano", "2062170298984652870")
    engine._state.save()
    source = FakeSource([
        Item(id="2062187928755867988", text="newest", url="https://nitter.net/FabrizioRomano/status/2062187928755867988#m"),
    ])
    dest = FakeDestination()
    engine._sources = {"FabrizioRomano": cast(NitterSource, source)}
    engine._destinations = {"futbol": cast(DiscordWebhookDestination, dest)}

    engine._process_source("FabrizioRomano", cast(NitterSource, source))

    assert dest.sent == [("2062187928755867988", "FabrizioRomano")]
    assert source.fetch_calls == ["2062170298984652870"]
