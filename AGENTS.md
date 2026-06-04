# AGENTS.md - Courier

Courier is a small Python daemon for many-to-many data routing: poll sources, dedupe items, and route them to destinations such as Discord webhooks.

## Project Rules

- Use `uv` for Python environment and dependency management.
- Keep all Python dependencies in `pyproject.toml`; do not add `requirements.txt`.
- Do not commit real secrets or runtime config:
  - `config.yaml` is local-only.
  - `state.json` is runtime state.
  - Discord webhook URLs must stay out of git.
- `config.example.yaml` should remain safe, realistic, and secret-free.
- Prefer channel-grouped routes in examples:
  ```yaml
  routes:
    - channel: futbol
      sources: [FabrizioRomano, David_Ornstein]
  ```
  The loader still supports legacy source-grouped routes for compatibility.
- Preserve the many-to-many architecture: sources, destinations, and routes are separate concepts.
- Future-proof source/destination work with explicit types and small interfaces rather than hard-coded one-off logic.

## Common Commands

```bash
uv sync
uv run courier -c config.yaml
uv run courier -c config.yaml -v
```

Container workflow:

```bash
make build
make run
make logs
```

Send a synthetic Discord test item:

```bash
make test-item
```

After config changes, restart only:

```bash
make restart
```

After code or dependency changes, rebuild and restart:

```bash
make rebuild
```

## Verification

Before claiming a change works, run the relevant checks for the change. At minimum:

```bash
uv sync
uv run python -m compileall -q src
uv run courier --help
uv run pytest
```

For container changes:

```bash
podman build -t courier:latest -f Containerfile .
podman run --rm courier:latest --help
```

For daemon/runtime changes, also verify logs:

```bash
podman ps --filter name=courier
podman logs --tail 80 courier
```

## Code Notes

- `src/courier/config.py` loads and validates YAML config.
- `src/courier/engine.py` owns the polling loop, route table, and orchestration.
- `src/courier/sources/` contains source interfaces and implementations.
- `src/courier/destinations/` contains destination interfaces and implementations.
- `src/courier/state.py` stores dedupe state.

## Reliability Expectations

- Treat dedupe/state updates carefully. Do not mark an item delivered before the required destinations have accepted it.
- Compare external numeric IDs numerically, not lexicographically.
- Be defensive around network APIs: timeouts, non-JSON error bodies, rate limits, transient failures.
- Prefer atomic state writes for files under `/data` or local state paths.
- Keep logs useful enough to answer: “Is it running? What did it poll? What did it send or skip?”

## Git Hygiene

- Keep generated/runtime files ignored: `.venv/`, `__pycache__/`, `*.pyc`, `config.yaml`, `state.json`, logs.
- Commit source, docs, lockfile, container packaging, and safe examples.
- Check `git status --short` before and after edits so user-owned local files are not accidentally swept into commits.
