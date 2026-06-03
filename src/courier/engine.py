"""Engine — poll loop, routing, and orchestration."""

from __future__ import annotations

import logging
import signal
import time

import httpx

from courier.config import Config
from courier.destinations.discord import DiscordWebhookDestination
from courier.sources.nitter import NitterSource
from courier.state import State

logger = logging.getLogger("courier")


class Engine:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._running = True
        self._state = State(config.settings.dedup_persistence)
        self._client = httpx.Client(timeout=15)

        # Build Nitter instance list (primary + other options)
        nitter_instances = [config.nitter_instances.primary] + config.nitter_instances.other_options

        # Build sources
        source_map = config.source_map()
        self._sources: dict[str, NitterSource] = {}
        for route in config.routes:
            scfg = source_map[route.source]
            if not scfg.active:
                continue
            if scfg.type != "nitter":
                logger.warning("Unsupported source type: %s", scfg.type)
                continue
            display_name = scfg.display_name or scfg.handle
            self._sources[scfg.handle] = NitterSource(
                handle=scfg.handle,
                display_name=display_name,
                nitter_instances=nitter_instances,
                client=self._client,
            )

        # Build destinations
        dest_map = config.destination_map()
        self._destinations: dict[str, DiscordWebhookDestination] = {}
        for dest in config.destinations:
            self._destinations[dest.id] = DiscordWebhookDestination(
                webhook_url=dest.webhook_url,
                client=self._client,
            )

        # Build route table: source_handle -> list of destination IDs
        self._route_table: dict[str, list[str]] = {}
        for route in config.routes:
            scfg = source_map[route.source]
            if not scfg.active:
                continue
            self._route_table[route.source] = route.destinations

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum: int, _frame) -> None:
        logger.info("Received signal %s, shutting down...", signum)
        self._running = False

    def run(self) -> None:
        interval = self._config.settings.poll_interval_minutes * 60
        logger.info(
            "Courier running — %d sources, %d destinations, poll every %ds",
            len(self._sources),
            len(self._destinations),
            interval,
        )

        while self._running:
            for handle, source in self._sources.items():
                if not self._running:
                    break
                since_id = self._state.get(handle)
                try:
                    items = source.fetch(since_id)
                except Exception:
                    logger.exception("Failed to fetch %s", handle)
                    continue

                if not items:
                    continue

                dest_ids = self._route_table.get(handle, [])
                if not dest_ids:
                    continue

                for item in items:
                    for dest_id in dest_ids:
                        dest = self._destinations.get(dest_id)
                        if dest is None:
                            continue
                        try:
                            dest.send(item, handle)
                        except Exception:
                            logger.exception(
                                "Failed to send %s to %s", item.id, dest_id
                            )

                # Update state to latest item ID and persist immediately
                self._state.set(handle, items[-1].id)
                self._state.save()

            if self._running:
                # Sleep in short intervals so we can catch shutdown signals
                for _ in range(interval):
                    if not self._running:
                        break
                    time.sleep(1)

        logger.info("Courier shut down.")
        self._state.save()
        self._client.close()