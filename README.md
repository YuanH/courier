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

uv run courier -c config.yaml --diagnose                  # probe every endpoint, then exit
uv run courier -c config.yaml --diagnose FabrizioRomano   # probe one source
```

`--diagnose` walks the same instance list the poll loop uses and reports what
each endpoint actually returned, so a feed that has gone quiet can be told apart
from an instance that is refusing you:

```
FabrizioRomano: OK
  [    empty-body] https://nitter.net/FabrizioRomano/rss  status=200 bytes=0
  [    http-error] https://xcancel.com/FabrizioRomano/rss  status=403 bytes=9
  [            ok] https://xcancel.com/FabrizioRomano/rss  status=200 bytes=4211 entries=20 newest=2062170298984652870
```

It exits non-zero when any source has no working endpoint, so it also works as
a health check.

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

Public Nitter instances are increasingly unreliable (bot protection, takedowns).
Courier fetches RSS from any working instance with automatic fallback, and
tolerates the ways these instances misbehave:

- an instance that answers `4xx` is retried once under a feed-reader
  User-Agent, because some hosts refuse browser-like clients on their RSS
  endpoints and others refuse everything else;
- blank bodies, HTML bot-challenge pages, and feeds with no tweet links are
  treated as failures, so the next instance gets a turn;
- byte-order marks and whitespace before the XML declaration are stripped, and
  a feed that parses into usable entries is kept even when the parser flags it
  (one stray `&` in a tweet should not cost you the whole feed).

One failure mode deserves its own mention, because it looks like success:
a provider can return a structurally valid feed whose only entry is a
whitelist or signup interstitial. HTTP status, XML validity, byte count and
entry count all look healthy. Courier therefore treats a provider as usable
only when the feed yields at least one `/status/<tweet-id>` link, and reports
anything else as `no-status-links`.

Providers rot faster than any list can be updated, so configure several:

```yaml
nitter_instances:
  - "https://xcancel.com"
  - "https://nitter.poast.org"
  - "https://nitter.tiekoetter.com"
  - "https://rsshub.example.com/twitter/user/{handle}"
```

Each entry is either a base URL, which gets Nitter's `/<handle>/rss` layout, or
a template naming `{handle}`. The template form is how a non-Nitter provider —
a self-hosted bridge, an RSSHub route, a per-handle feed from a hosted service
— joins the same fallback chain without any new code. The older
`primary`/`fallback`/`other_options` mapping still loads.

When feeds go quiet, run `--diagnose` first: it tells you which providers
answered and how. If you have a self-hosted instance, list it first.

## License

MIT