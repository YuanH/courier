"""Configuration loading and validation."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml


@dataclasses.dataclass
class NitterSettings:
    primary: str
    fallback: str
    other_options: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Settings:
    poll_interval_minutes: int = 5
    dedup_persistence: str = "state.json"
    nitter_fallback: str = "xcancel.com"


@dataclasses.dataclass
class Source:
    handle: str
    type: str = "nitter"
    display_name: str = ""
    active: bool = True
    url: str = ""
    subreddit: str = ""
    channel_id: str = ""


@dataclasses.dataclass
class Destination:
    id: str
    webhook_url: str
    display_name: str = ""


@dataclasses.dataclass
class Route:
    source: str
    destinations: list[str]


@dataclasses.dataclass
class Config:
    settings: Settings = dataclasses.field(default_factory=Settings)
    nitter_instances: NitterSettings = dataclasses.field(
        default_factory=lambda: NitterSettings(
            primary="https://nitter.net", fallback="https://xcancel.com"
        )
    )
    sources: list[Source] = dataclasses.field(default_factory=list)
    destinations: list[Destination] = dataclasses.field(default_factory=list)
    routes: list[Route] = dataclasses.field(default_factory=list)

    def source_map(self) -> dict[str, Source]:
        return {s.handle: s for s in self.sources}

    def destination_map(self) -> dict[str, Destination]:
        return {d.id: d for d in self.destinations}

    def route_map(self) -> dict[str, list[str]]:
        return {r.source: r.destinations for r in self.routes}


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    raw = yaml.safe_load(path.read_text())
    if not raw:
        raise ValueError("Empty config file")

    settings_raw = raw.get("settings", {})
    settings = Settings(
        poll_interval_minutes=settings_raw.get("poll_interval_minutes", 5),
        dedup_persistence=settings_raw.get("dedup_persistence", "state.json"),
        nitter_fallback=settings_raw.get("nitter_fallback", "xcancel.com"),
    )

    nitter_raw = raw.get("nitter_instances", {})
    nitter = NitterSettings(
        primary=nitter_raw.get("primary", "https://nitter.net"),
        fallback=nitter_raw.get("fallback", "https://xcancel.com"),
        other_options=nitter_raw.get("other_options", []),
    )

    sources = [Source(**s) for s in raw.get("sources", [])]
    destinations = [Destination(**d) for d in raw.get("destinations", [])]
    routes = [Route(**r) for r in raw.get("routes", [])]

    # Validation
    known_sources = {s.handle for s in sources}
    known_dests = {d.id for d in destinations}
    for route in routes:
        if route.source not in known_sources:
            raise ValueError(f"Route references unknown source: {route.source}")
        for dest in route.destinations:
            if dest not in known_dests:
                raise ValueError(
                    f"Route for {route.source} references unknown destination: {dest}"
                )

    return Config(
        settings=settings,
        nitter_instances=nitter,
        sources=sources,
        destinations=destinations,
        routes=routes,
    )