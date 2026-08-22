"""Courier — many-to-many data routing daemon."""

from __future__ import annotations

import argparse
import logging
import sys

from courier.config import load_config
from courier.engine import Engine
from courier.sources.base import ProbeResult


def _print_diagnosis(report: dict[str, list[ProbeResult]]) -> int:
    """Print per-endpoint probe results. Returns a shell exit code."""
    if not report:
        print("No active sources are configured; nothing to diagnose.")
        return 1

    unhealthy = 0
    for handle, results in report.items():
        healthy = any(r.ok for r in results)
        if not healthy:
            unhealthy += 1
        print(f"\n{handle}: {'OK' if healthy else 'NO WORKING ENDPOINT'}")
        if not results:
            print("  (this source type does not support probing)")
            continue
        for r in results:
            status = r.status if r.status is not None else "-"
            line = f"  [{r.outcome:>14}] {r.endpoint}  status={status} bytes={r.bytes}"
            if r.ok:
                line += f" entries={r.entries} newest={r.item_ids[0] if r.item_ids else '-'}"
            print(line)
            if r.detail:
                print(f"                   {r.detail}")

    print(f"\n{len(report) - unhealthy}/{len(report)} sources have a working endpoint.")
    return 1 if unhealthy else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Courier — many-to-many data routing")
    parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--diagnose",
        nargs="?",
        const="",
        metavar="HANDLE",
        help=(
            "Probe every configured endpoint for each source (or just HANDLE) "
            "and report why each one succeeds or fails, then exit"
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    engine = Engine(config)

    if args.diagnose is not None:
        handle = args.diagnose or None
        sys.exit(_print_diagnosis(engine.diagnose(handle)))

    engine.run()


if __name__ == "__main__":
    main()
