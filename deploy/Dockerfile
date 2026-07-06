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

# `postgresql-client` du dépôt Debian de la base flotte avec le codename de
# python:3.12-slim (bookworm/trixie/…) : selon le build, on peut se retrouver
# avec un pg_dump 15 face à un serveur 16 ("server version mismatch"), ce qui
# casse la feature de backup interne. On installe explicitement
# postgresql-client-16 depuis le dépôt PGDG pour rester aligné avec l'image
# `postgres:16-alpine` utilisée en compose (deploy/docker-compose*.yml).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
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

# Utilisateur non-root : uvicorn ne doit jamais servir le trafic en root.
# /data accueille les dumps temporaires de sauvegarde (backup/worker.py) et
# doit rester writable par cet utilisateur.
RUN useradd -r -u 10001 -d /app -s /usr/sbin/nologin docflow \
    && mkdir -p /data \
    && chown -R docflow:docflow /app /data

USER docflow

EXPOSE 8080

# Aucun secret en ENV — tout vient de /data/.env au runtime
CMD ["uvicorn", "docflow.app:app", "--host", "0.0.0.0", "--port", "8080"]
