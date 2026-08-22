"""Configuration loading and validation."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml


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
    channel_id: str = ""


@dataclasses.dataclass
class Destination:
    id: str
    webhook_url: str
    type: str = "discord"
    display_name: str = ""


@dataclasses.dataclass
class Route:
    source: str
    destinations: list[str]


@dataclasses.dataclass
class Config:
    settings: Settings = dataclasses.field(default_factory=Settings)
    # Ordered list of X/Twitter RSS providers, tried until one yields tweets.
    nitter_instances: list[str] = dataclasses.field(default_factory=list)
    sources: list[Source] = dataclasses.field(default_factory=list)
    destinations: list[Destination] = dataclasses.field(default_factory=list)
    routes: list[Route] = dataclasses.field(default_factory=list)

    def source_map(self) -> dict[str, Source]:
        return {s.handle: s for s in self.sources}

    def destination_map(self) -> dict[str, Destination]:
        return {d.id: d for d in self.destinations}

    def route_map(self) -> dict[str, list[str]]:
        return {r.source: r.destinations for r in self.routes}


def _load_nitter_instances(raw) -> list[str]:
    """Accept either an ordered list of providers or the legacy mapping form.

    The list form is preferred: recovering from an outage means trying many
    providers, and ``primary``/``fallback`` only names two of them. Entries may
    be a base URL (``https://host`` -> ``https://host/<handle>/rss``) or a
    template containing ``{handle}`` for providers that shape URLs differently.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(entry) for entry in raw if entry]
    if isinstance(raw, dict):
        ordered = [raw.get("primary", ""), raw.get("fallback", "")]
        ordered.extend(raw.get("other_options", []) or [])
        return [str(entry) for entry in ordered if entry]
    raise ValueError(
        "nitter_instances must be a list of provider URLs "
        "or a mapping with primary/fallback/other_options"
    )


def _load_routes(routes_raw: list[dict]) -> list[Route]:
    """Load routes from source-grouped or channel-grouped config entries."""
    routes: list[Route] = []
    for entry in routes_raw:
        if "source" in entry:
            routes.append(Route(**entry))
            continue

        if "channel" in entry:
            destination = entry["channel"]
            for source in entry.get("sources", []):
                routes.append(Route(source=source, destinations=[destination]))
            continue

        raise ValueError("Route must define either 'source' or 'channel'")

    return routes


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

    nitter = _load_nitter_instances(raw.get("nitter_instances"))

    sources = [Source(**s) for s in raw.get("sources", [])]
    destinations = [Destination(**d) for d in raw.get("destinations", [])]
    routes = _load_routes(raw.get("routes", []))

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