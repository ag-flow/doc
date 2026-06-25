#!/usr/bin/env bash
# dev-deploy.sh — Redéploiement de docflow sur la VM de test.
# À exécuter directement sur la VM en root (cd /opt/docflow && ./scripts/dev-deploy.sh).
# Idempotent : peut être relancé sans danger.
# Initialise /data/.env et /data/pg_password.txt s'ils n'existent pas.
#
# Usage :
#   ./scripts/dev-deploy.sh [BRANCH]
#   ex : ./scripts/dev-deploy.sh dev

set -euo pipefail
IFS=$'\n\t'

APP_DIR="${APP_DIR:-/opt/docflow}"
COMPOSE_FILE="deploy/docker-compose.yml"

# ─── Argument : branche cible ─────────────────────────────────────────────────
TARGET_BRANCH=""
for arg in "$@"; do
    case "$arg" in
        --*) echo "ERREUR : flag inconnu : $arg" >&2; exit 1 ;;
        *)
            if [[ -n "$TARGET_BRANCH" ]]; then
                echo "ERREUR : plusieurs branches passées en argument." >&2; exit 1
            fi
            TARGET_BRANCH="$arg"
            ;;
    esac
done

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERREUR : ce script doit être exécuté en root." >&2
    exit 1
fi

cd "$APP_DIR"

# ─── 0) Initialisation de /data (idempotent) ──────────────────────────────────
echo "==> [0/3] Vérification de /data..."
mkdir -p /data

if [[ ! -f /data/pg_password.txt ]]; then
    echo "  → Génération du mot de passe Postgres..."
    python3 -c "import secrets; print(secrets.token_hex(24))" > /data/pg_password.txt
    chmod 600 /data/pg_password.txt
    echo "  ✓ /data/pg_password.txt créé"
fi

PG_PASSWORD="$(cat /data/pg_password.txt)"

if [[ ! -f /data/.env ]]; then
    echo "  → Génération de /data/.env avec des secrets aléatoires (dev)..."
    JWT_SECRET="$(python3 -c "import secrets; print(secrets.token_hex(32))")"
    ADMIN_PASSWORD="$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")"
    cat > /data/.env <<EOF
# Généré automatiquement par dev-deploy.sh — NE PAS COMMITTER
DATABASE_URL=postgresql://docflow:${PG_PASSWORD}@postgres:5432/docflow
JWT_SECRET=${JWT_SECRET}
BOOTSTRAP_ADMIN_EMAIL=admin@docflow.local
BOOTSTRAP_ADMIN_PASSWORD=${ADMIN_PASSWORD}
BOOTSTRAP_ADMIN_LABEL=Admin
LOG_LEVEL=INFO
EOF
    chmod 600 /data/.env
    echo "  ✓ /data/.env créé"
    echo ""
    echo "  ┌─ Identifiants bootstrap admin ────────────────────┐"
    echo "  │  Email    : admin@docflow.local                   │"
    echo "  │  Password : ${ADMIN_PASSWORD}  │"
    echo "  └───────────────────────────────────────────────────┘"
    echo ""
else
    echo "  ✓ /data/.env existant conservé"
fi

# ─── 1) Git pull ──────────────────────────────────────────────────────────────
if [[ -n "$TARGET_BRANCH" ]]; then
    echo "==> [1/3] Switch vers ${TARGET_BRANCH} + pull..."
    git fetch origin
    git checkout "$TARGET_BRANCH"
    git pull --ff-only origin "$TARGET_BRANCH"
else
    CURRENT="$(git branch --show-current)"
    echo "==> [1/3] Pull (${CURRENT})..."
    git pull --ff-only
fi

# ─── 2) Build + redémarrage ───────────────────────────────────────────────────
echo ""
echo "==> [2/3] Build de l'image Docker..."
docker compose -f "$COMPOSE_FILE" build

echo ""
echo "==> Redémarrage de la stack..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans || true
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

echo ""
docker compose -f "$COMPOSE_FILE" ps

# ─── 3) Smoke /health ─────────────────────────────────────────────────────────
echo ""
echo "==> [3/3] Smoke /health (timeout 90s)..."
SMOKE_OK=0
ELAPSED=0
while [[ $ELAPSED -lt 90 ]]; do
    if curl -sf -m 3 "http://localhost:8080/health" &>/dev/null; then
        SMOKE_OK=1; break
    fi
    sleep 5
    ELAPSED=$(( ELAPSED + 5 ))
done

if [[ $SMOKE_OK -eq 1 ]]; then
    echo ""
    echo "  ✓ docflow opérationnel — http://localhost:8080/health"
else
    echo "" >&2
    echo "  ✗ /health ne répond pas après 90s" >&2
    echo "  Vérifier : docker compose -f ${COMPOSE_FILE} logs --tail=80 app" >&2
    exit 1
fi

echo ""
echo "==> Logs (80 dernières lignes) :"
docker compose -f "$COMPOSE_FILE" logs --tail=80
