"""Send a synthetic Courier item through configured Discord destinations.

This is an operational smoke test: it does not poll Nitter, but it uses the same
config loader and Discord webhook destination code as the daemon.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

import httpx

from courier.config import load_config
from courier.destinations.discord import DiscordWebhookDestination
from courier.sources.base import Item


def _default_source_and_destinations(config):
    active_sources = {source.handle for source in config.sources if source.active}
    for route in config.routes:
        if route.source in active_sources and route.destinations:
            return route.source, route.destinations
    raise SystemExit("No active routed sources found in config")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test Courier item to Discord")
    parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")
    parser.add_argument("--source", help="Source handle to impersonate; defaults to first active routed source")
    parser.add_argument(
        "--dest",
        action="append",
        dest="destinations",
        help="Destination id to send to. Repeat for multiple. Defaults to source route destinations.",
    )
    parser.add_argument(
        "--text",
        default="https://fxtwitter.com/RealXavier011/status/2062000574208307702?s=20",
        help="Test item text; not used by Discord link payloads",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    source_map = config.source_map()
    dest_map = config.destination_map()
    route_map = config.route_map()

    default_source, default_destinations = _default_source_and_destinations(config)
    source_handle = args.source or default_source
    if source_handle not in source_map:
        raise SystemExit(f"Unknown source: {source_handle}")

    destination_ids = args.destinations or route_map.get(source_handle) or default_destinations
    unknown_destinations = [dest_id for dest_id in destination_ids if dest_id not in dest_map]
    if unknown_destinations:
        raise SystemExit(f"Unknown destinations: {', '.join(unknown_destinations)}")

    source = source_map[source_handle]
    display_name = source.display_name or source.handle
    now = datetime.now(timezone.utc)
    item = Item(
        id=f"courier-test-{int(now.timestamp())}",
        text=args.text,
        url="https://x.com/RealXavier011/status/2062000574208307702?s=20",
        author=display_name,
        timestamp=now.isoformat(),
    )

    with httpx.Client(timeout=15) as client:
        for dest_id in destination_ids:
            dest = dest_map[dest_id]
            webhook = DiscordWebhookDestination(dest.webhook_url, client=client)
            webhook.send(item, display_name)
            print(f"sent test item from {source_handle} to {dest_id}")


if __name__ == "__main__":
    main()
