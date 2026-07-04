#!/usr/bin/env bash
# dev-deploy.sh — Redéploiement de docflow sur la VM de test.
# À exécuter à la racine du repo, en root : sudo ./dev-deploy.sh [BRANCH]
# Idempotent : peut être relancé sans danger.
#
# /data/.env est initialisé par copie de deploy/.env.example, puis réparé
# clé par clé : chaque secret manquant OU VIDE est régénéré individuellement
# (un .env partiel est complété, jamais ignoré ni écrasé).
#
# Usage :
#   sudo ./dev-deploy.sh [BRANCH]
#   ex : sudo ./dev-deploy.sh dev

set -euo pipefail
IFS=$'\n\t'

# Tout le script vit dans main() : bash parse le fichier entier avant de
# l'exécuter, ce qui rend le `git reset --hard` de l'étape 1 inoffensif
# même quand il remplace ce fichier pendant l'exécution.
main() {
    local APP_DIR="${APP_DIR:-/opt/docflow}"
    local DATA_ROOT="${DATA_ROOT:-/data}"
    local ENV_FILE="${DATA_ROOT}/.env"
    local PG_PASSWORD_FILE="${DATA_ROOT}/pg_password.txt"
    local COMPOSE_FILE="deploy/docker-compose.yml"

    # ─── Argument : branche cible ─────────────────────────────────────────────
    local TARGET_BRANCH=""
    local arg
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
        echo "ERREUR : ce script doit être exécuté en root (sudo ./dev-deploy.sh)." >&2
        exit 1
    fi

    cd "$APP_DIR"

    # ─── 1) Git sync ──────────────────────────────────────────────────────────
    # reset --hard (et non pull --ff-only) : robuste quand le script se met à
    # jour lui-même lors de la synchro — cf. main() ci-dessus.
    if [[ -n "$TARGET_BRANCH" ]]; then
        echo "==> [1/4] Sync vers ${TARGET_BRANCH}..."
        git fetch origin
        git checkout "$TARGET_BRANCH"
        git reset --hard "origin/${TARGET_BRANCH}"
    else
        local CURRENT
        CURRENT="$(git branch --show-current)"
        echo "==> [1/4] Sync (${CURRENT})..."
        git fetch origin
        git reset --hard "origin/${CURRENT}"
    fi

    # ─── 2) Initialisation + réparation de /data ──────────────────────────────
    echo ""
    echo "==> [2/4] Vérification de ${DATA_ROOT}..."
    mkdir -p "$DATA_ROOT"

    # Mot de passe Postgres : fichier séparé (consommé par compose via
    # secrets:/POSTGRES_PASSWORD_FILE), réparé s'il est absent OU vide.
    if [[ ! -s "$PG_PASSWORD_FILE" ]]; then
        echo "  → Génération du mot de passe Postgres..."
        openssl rand -hex 24 > "$PG_PASSWORD_FILE"
        chmod 600 "$PG_PASSWORD_FILE"
        echo "  ✓ ${PG_PASSWORD_FILE} créé"
    fi

    local FIRST_ENV=0
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "  → .env absent — initialisation depuis deploy/.env.example..."
        cp deploy/.env.example "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        FIRST_ENV=1
    fi

    # Complétion des valeurs manquantes ou vides : chaque clé est vérifiée
    # individuellement (un .env partiel doit être réparé, pas ignoré).
    _env_get() { grep -m1 "^${1}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '\r' || true; }
    _env_set() {
        local key="$1" val="$2"
        if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
        else
            echo "${key}=${val}" >> "$ENV_FILE"
        fi
    }

    if [[ -z "$(_env_get DATABASE_URL)" ]]; then
        # pg_password.txt est la source de vérité : le volume pgdata a été
        # initialisé avec ce mot de passe.
        local PG_PASSWORD
        PG_PASSWORD="$(cat "$PG_PASSWORD_FILE")"
        _env_set DATABASE_URL "postgresql://docflow:${PG_PASSWORD}@postgres:5432/docflow"
        echo "  ✓ DATABASE_URL reconstruite depuis ${PG_PASSWORD_FILE}"
    fi

    if [[ -z "$(_env_get JWT_SECRET)" ]]; then
        _env_set JWT_SECRET "$(openssl rand -hex 32)"
        echo "  ✓ JWT_SECRET généré"
    fi

    if [[ -z "$(_env_get ENCRYPTION_KEY)" ]]; then
        # Clé Fernet : 32 octets base64-urlsafe (openssl rand -base64 ne convient pas).
        _env_set ENCRYPTION_KEY "$(python3 -c \
            "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")"
        echo "  ✓ ENCRYPTION_KEY générée"
    fi

    unset -f _env_get _env_set

    if [[ "$FIRST_ENV" -eq 1 ]]; then
        echo ""
        echo "  ┌─ Premier accès ────────────────────────────────────────────────┐"
        echo "  │  Aucun admin n'est pré-créé. Créer le premier compte via :      │"
        echo "  │  POST /api/setup/init-admin (wizard exposé par l'app au         │"
        echo "  │  premier démarrage, tant qu'aucun utilisateur n'existe).        │"
        echo "  └──────────────────────────────────────────────────────────────────┘"
        echo ""
    else
        echo "  ✓ ${ENV_FILE} existant conservé (clés vides réparées le cas échéant)"
    fi

    # ─── 3) Build + redémarrage ───────────────────────────────────────────────
    echo ""
    echo "==> [3/4] Build de l'image Docker..."
    docker compose -f "$COMPOSE_FILE" build

    echo ""
    echo "==> Redémarrage de la stack..."
    docker compose -f "$COMPOSE_FILE" down --remove-orphans || true
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

    echo ""
    docker compose -f "$COMPOSE_FILE" ps

    # ─── 4) Smoke /health ─────────────────────────────────────────────────────
    echo ""
    echo "==> [4/4] Smoke /health (timeout 90s)..."
    local SMOKE_OK=0
    local ELAPSED=0
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
}

main "$@"
