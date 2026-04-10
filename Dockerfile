# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: Abhängigkeiten installieren (reproduzierbar via uv.lock)
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# uv installieren
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock send_message.py ./

RUN uv sync --frozen --no-dev --no-editable

# ---------------------------------------------------------------------------
# Stage 2: Minimales Runtime-Image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Non-root User
RUN useradd --system --create-home --uid 1000 webex

# Venv aus Build-Stage übernehmen
COPY --from=builder /build/.venv /venv

# Datenverzeichnis für config.json und roomlist.json
RUN mkdir -p /data && chown webex:webex /data

USER webex

ENV PATH="/venv/bin:$PATH" \
    WEBEX_CONFIG_DIR=/data

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health')"

ENTRYPOINT ["webex", "serve"]
CMD ["--host", "0.0.0.0", "--port", "9000"]
