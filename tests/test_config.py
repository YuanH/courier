from pathlib import Path

from courier.config import load_config


def write_config(tmp_path: Path, routes: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
settings:
  poll_interval_minutes: 5
nitter_instances:
  primary: https://nitter.net
  fallback: https://xcancel.com
sources:
  - handle: nickkokonas
    display_name: nick kokonas
    type: nitter
    active: true
  - handle: GSpier
    display_name: Guy Spier
    type: nitter
    active: true
  - handle: iximiuz
    display_name: Ivan Velichko
    type: nitter
    active: true
destinations:
  - id: investing
    webhook_url: https://discord.invalid/investing
  - id: engineering
    webhook_url: https://discord.invalid/engineering
routes:
{routes}
"""
    )
    return path


def test_load_config_accepts_channel_grouped_routes(tmp_path):
    path = write_config(
        tmp_path,
        """  - channel: investing
    sources:
      - nickkokonas
      - GSpier
  - channel: engineering
    sources:
      - iximiuz
""",
    )

    cfg = load_config(path)

    assert [(route.source, route.destinations) for route in cfg.routes] == [
        ("nickkokonas", ["investing"]),
        ("GSpier", ["investing"]),
        ("iximiuz", ["engineering"]),
    ]


def test_load_config_accepts_mixed_legacy_and_channel_grouped_routes(tmp_path):
    path = write_config(
        tmp_path,
        """  - source: nickkokonas
    destinations: [investing]
  - channel: engineering
    sources:
      - iximiuz
""",
    )

    cfg = load_config(path)

    assert [(route.source, route.destinations) for route in cfg.routes] == [
        ("nickkokonas", ["investing"]),
        ("iximiuz", ["engineering"]),
    ]


def test_load_config_rejects_channel_grouped_route_with_unknown_destination(tmp_path):
    path = write_config(
        tmp_path,
        """  - channel: unknown-channel
    sources:
      - iximiuz
""",
    )

    try:
        load_config(path)
    except ValueError as exc:
        assert "unknown destination" in str(exc)
        assert "unknown-channel" in str(exc)
    else:
        raise AssertionError("expected ValueError")
