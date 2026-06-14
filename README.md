# Courier

**Many-to-many data routing.** Poll sources, route to destinations.

```
@FabrizioRomano ──────►│        │──► Discord #futbol
@David_Ornstein ──────►│ Courier │──► Discord #transfers
@TheAthleticFC  ──────►│        │──► Discord general
                        └────────┘
```

## Quickstart

```bash
uv sync

cp config.example.yaml config.yaml
# Edit config.yaml with your webhook URLs

uv run courier -c config.yaml
```

## Usage

```
uv run courier -c config.yaml        # run with config
uv run courier -c config.yaml -v      # debug logging
```

## Podman

Build and run as a container:

```bash
make build
make run
```

Or manually:

```bash
podman build -t courier:latest -f Containerfile .
podman run -d \
  --name courier \
  --replace \
  --restart=unless-stopped \
  -v "$PWD/config.yaml:/config/config.yaml:ro" \
  -v courier-data:/data \
  courier:latest
```

Check it:

```bash
make ps
make logs
make data
```

Send a synthetic test item through the configured Discord webhook:

```bash
make test-item
```

Stop it:

```bash
make stop
```

Rebuild and relaunch after code or dependency changes:

```bash
make rebuild
```

The container reads `/config/config.yaml` and writes state to `/data/state.json` when `settings.dedup_persistence` is `state.json`. Because `config.yaml` is bind-mounted, editing config does not require rebuilding the image; restart the container with `make restart` so Courier reloads the file.

## Configuration

See `config.example.yaml`. Key structure:

- **sources** — data origins (`type: nitter` for X/Twitter, `type: youtube` for YouTube channels)
- **destinations** — where to send (`type: discord` webhook URLs)
- **routes** — which sources go to which destinations

Sources and destinations are resolved through a type registry
(`courier.sources.SOURCE_TYPES`, `courier.destinations.DESTINATION_TYPES`), so
adding a new kind means writing one class and registering it — no engine changes.

## YouTube

YouTube channels are polled via their public per-channel RSS feed — no API key,
no quota. Identify a channel by:

- its `channel_id` (`UC…`, most reliable),
- an `@handle` (e.g. `@mkbhd`), or
- a channel URL.

Courier resolves a handle/URL to a channel id on the first poll and caches it.
New uploads are posted as plain watch links so Discord renders the native video
embed. Because video IDs aren't ordered, YouTube dedupe is keyed on each video's
publish time, so `state.json` stores a timestamp for YouTube sources (and a
numeric status ID for Nitter sources).

## Future Sources

The plugin model makes these straightforward to add next:
- RSS/Atom feeds
- Reddit subreddits
- Generic webhooks

## Nitter Note

Public Nitter instances are increasingly unreliable (bot protection, takedowns). The code correctly fetches RSS from any working instance with automatic fallback. If you have a self-hosted Nitter instance, point `nitter_instances.primary` at it for best results.

## License

MIT