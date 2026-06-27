# deploy/Dockerfile
# Image de production docflow — aucun secret embarqué (§sécurité CLAUDE.md)
# Build : docker build -f deploy/Dockerfile -t docflow:latest .

# --- Stage 1 : build du frontend ---
FROM node:22-slim AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2 : image Python de production ---
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Dépendances d'abord (layer cachée si seul le code change)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --no-dev --no-install-project --frozen

# Code source + migrations SQL + templates YAML
COPY backend/src/ ./src/
COPY backend/migrations/ ./migrations/
COPY templates/ ./templates/
RUN uv sync --no-dev --frozen

# Assets frontend
COPY --from=frontend-builder /build/dist ./static

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

# Aucun secret en ENV — tout vient de /data/.env au runtime
CMD ["uvicorn", "docflow.app:app", "--host", "0.0.0.0", "--port", "8080"]
