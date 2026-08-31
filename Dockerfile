# Beatster — single-container build: compiles the frontend, then serves
# API + WebSockets + static files from one FastAPI process.

FROM node:22-alpine AS frontend
RUN npm install -g pnpm@10
WORKDIR /build
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY backend/tools ./tools
COPY --from=frontend /build/dist ./static
# bundled pre-built song catalog — copied into the data volume on first start
COPY data/catalog.json ./seed/catalog.json

ENV BEATSTER_DATA_DIR=/data \
    BEATSTER_STATIC_DIR=/app/static
VOLUME /data
EXPOSE 8000

CMD ["/bin/sh", "-c", "\
  if [ ! -f \"$BEATSTER_DATA_DIR/catalog.json\" ] && [ -f /app/seed/catalog.json ]; then \
    mkdir -p \"$BEATSTER_DATA_DIR\" && cp /app/seed/catalog.json \"$BEATSTER_DATA_DIR/\" && \
    echo \"seeded catalog cache into $BEATSTER_DATA_DIR\"; \
  fi; \
  exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]
