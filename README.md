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

## Configuration

See `config.example.yaml`. Key structure:

- **sources** — data origins (type: `nitter` for X/Twitter)
- **destinations** — where to send (webhook URLs)
- **routes** — which sources go to which destinations

## Future Sources

The plugin model supports adding:
- RSS/Atom feeds
- Reddit subreddits
- YouTube channels
- Generic webhooks

## Nitter Note

Public Nitter instances are increasingly unreliable (bot protection, takedowns). The code correctly fetches RSS from any working instance with automatic fallback. If you have a self-hosted Nitter instance, point `nitter_instances.primary` at it for best results.

## License

MIT