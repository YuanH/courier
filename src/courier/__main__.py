"""Courier — many-to-many data routing daemon."""

from __future__ import annotations

import argparse
import logging
import sys

from courier.config import load_config
from courier.engine import Engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Courier — many-to-many data routing")
    parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
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
    engine.run()


if __name__ == "__main__":
    main()