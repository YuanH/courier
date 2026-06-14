"""Engine — poll loop, routing, and orchestration."""

from __future__ import annotations

import logging
import signal
import time

import httpx

from courier.config import Config
from courier.destinations import UnsupportedDestinationType, build_destination
from courier.destinations.base import Destination
from courier.sources import SourceContext, UnsupportedSourceType, build_source
from courier.sources.base import Source
from courier.state import State

logger = logging.getLogger("courier")


class Engine:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._running = True
        self._state = State(config.settings.dedup_persistence)
        self._client = httpx.Client(timeout=15)

        # Shared build context for sources (Nitter instance list + HTTP client).
        nitter_instances = [config.nitter_instances.primary] + config.nitter_instances.other_options
        ctx = SourceContext(client=self._client, nitter_instances=nitter_instances)

        # Build sources via the type registry; a source may appear in several
        # routes, so build each handle once.
        source_map = config.source_map()
        self._sources: dict[str, Source] = {}
        for route in config.routes:
            scfg = source_map[route.source]
            if not scfg.active or scfg.handle in self._sources:
                continue
            try:
                self._sources[scfg.handle] = build_source(scfg, ctx)
            except UnsupportedSourceType as exc:
                logger.warning("Skipping source: %s", exc)

        # Build destinations via the type registry.
        self._destinations: dict[str, Destination] = {}
        for dest in config.destinations:
            try:
                self._destinations[dest.id] = build_destination(dest, self._client)
            except UnsupportedDestinationType as exc:
                logger.warning("Skipping destination: %s", exc)

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
                self._process_source(handle, source)

            if self._running:
                # Sleep in short intervals so we can catch shutdown signals
                for _ in range(interval):
                    if not self._running:
                        break
                    time.sleep(1)

        logger.info("Courier shut down.")
        self._state.save()
        self._client.close()

    def _process_source(self, handle: str, source: Source) -> None:
        since_id = self._state.get(handle)
        try:
            items = source.fetch(since_id)
        except Exception:
            logger.exception("Failed to fetch %s", handle)
            return

        if not items:
            logger.info("No new items for %s since %s", handle, since_id or "<bootstrap>")
            return

        latest_id = items[-1].id
        if since_id is None:
            logger.info(
                "Bootstrapping %s with latest item %s; suppressing %d historical items",
                handle,
                latest_id,
                len(items),
            )
            self._state.set(handle, latest_id)
            self._state.save()
            return

        dest_ids = self._route_table.get(handle, [])
        if not dest_ids:
            logger.warning("No destinations configured for %s; not advancing state", handle)
            return

        for item in items:
            for dest_id in dest_ids:
                dest = self._destinations.get(dest_id)
                if dest is None:
                    logger.warning("Unknown destination %s for %s", dest_id, handle)
                    continue
                try:
                    logger.info("Sending %s from %s to %s", item.id, handle, dest_id)
                    dest.send(item, handle)
                    logger.info("Sent %s from %s to %s", item.id, handle, dest_id)
                except Exception:
                    logger.exception("Failed to send %s to %s", item.id, dest_id)

        # Update state to latest item ID and persist immediately.
        self._state.set(handle, latest_id)
        self._state.save()
