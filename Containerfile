FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies from the locked uv environment first for better layer caching.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev

# Runtime working directory. Keep config read-only under /config and mutable state under /data.
WORKDIR /data

ENTRYPOINT ["uv", "run", "--project", "/app", "--no-sync", "courier"]
CMD ["-c", "/config/config.yaml"]
