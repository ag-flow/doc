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
#
# Reset du mot de passe d'un compte admin (stack déjà démarrée, aucune
# synchro git ni rebuild) :
#   sudo ./dev-deploy.sh --resetadmin [EMAIL]
#   EMAIL optionnel si un seul compte admin existe en base.

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

    # ─── Arguments ────────────────────────────────────────────────────────────
    local TARGET_BRANCH=""
    local RESETADMIN=0
    local ADMIN_EMAIL=""
    local arg
    for arg in "$@"; do
        case "$arg" in
            --resetadmin) RESETADMIN=1 ;;
            --*) echo "ERREUR : flag inconnu : $arg" >&2; exit 1 ;;
            *)
                if [[ "$RESETADMIN" -eq 1 ]]; then
                    if [[ -n "$ADMIN_EMAIL" ]]; then
                        echo "ERREUR : plusieurs emails passés en argument." >&2; exit 1
                    fi
                    ADMIN_EMAIL="$arg"
                elif [[ -n "$TARGET_BRANCH" ]]; then
                    echo "ERREUR : plusieurs branches passées en argument." >&2; exit 1
                else
                    TARGET_BRANCH="$arg"
                fi
                ;;
        esac
    done

    if [[ "$(id -u)" -ne 0 ]]; then
        echo "ERREUR : ce script doit être exécuté en root (sudo ./dev-deploy.sh)." >&2
        exit 1
    fi

    cd "$APP_DIR"

    if [[ "$RESETADMIN" -eq 1 ]]; then
        reset_admin_password "$COMPOSE_FILE" "$ADMIN_EMAIL"
        return 0
    fi

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

    if [[ $SMOKE_OK -ne 1 ]]; then
        echo "" >&2
        echo "  ✗ /health ne répond pas après 90s" >&2
        echo "  Vérifier : docker compose -f ${COMPOSE_FILE} logs --tail=80 app" >&2
        exit 1
    fi

    # ─── Récapitulatif ────────────────────────────────────────────────────────
    local IP ADMIN_INFO
    IP="$(hostname -I | awk '{print $1}')"
    # docflow n'a pas de mot de passe bootstrap : le premier compte se crée via
    # le wizard init-admin, qui se désactive dès qu'un utilisateur existe.
    if curl -sf -m 3 "http://localhost:8080/api/setup/status" 2>/dev/null \
            | grep -q '"needs_setup": *true'; then
        ADMIN_INFO="aucun compte — créer le premier admin :
            curl -X POST http://${IP}:8080/api/setup/init-admin \\
                 -H 'Content-Type: application/json' \\
                 -d '{\"username\":\"admin\",\"email\":\"admin@example.org\",\"password\":\"...\"}'"
    else
        ADMIN_INFO="compte admin déjà initialisé (wizard désactivé)"
    fi

    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""
    echo "  ✓ docflow opérationnel"
    echo ""
    echo "  Accès : http://${IP}:8080"
    echo "  Santé : http://${IP}:8080/health"
    echo "  Admin : ${ADMIN_INFO}"
    echo "  Env   : ${ENV_FILE} (+ ${PG_PASSWORD_FILE})"
    echo ""
    echo "  Logs  : docker compose -f ${COMPOSE_FILE} logs -f app"
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
}

# ─── Reset du mot de passe d'un compte admin ──────────────────────────────────
# Stack déjà démarrée requise ; ne touche ni au dépôt git ni à l'image.
reset_admin_password() {
    local COMPOSE_FILE="$1"
    local TARGET_EMAIL="$2"

    echo "==> Reset du mot de passe admin..."

    local RUNNING
    RUNNING="$(docker compose -f "$COMPOSE_FILE" ps --services --status running)"
    if ! grep -qx "app" <<<"$RUNNING" || ! grep -qx "postgres" <<<"$RUNNING"; then
        echo "ERREUR : la stack n'est pas démarrée (app + postgres) — lancer un déploiement d'abord." >&2
        exit 1
    fi

    if [[ -z "$TARGET_EMAIL" ]]; then
        local ADMIN_LIST ADMIN_COUNT
        ADMIN_LIST="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U docflow -d docflow -tA -c \
            "SELECT email FROM app_user WHERE is_admin = true ORDER BY email;")"
        ADMIN_COUNT="$(grep -c . <<<"$ADMIN_LIST" || true)"
        if [[ "$ADMIN_COUNT" -eq 0 ]]; then
            echo "ERREUR : aucun compte admin en base." >&2
            exit 1
        elif [[ "$ADMIN_COUNT" -gt 1 ]]; then
            echo "ERREUR : plusieurs comptes admin, préciser l'email :" >&2
            sed 's/^/  - /' <<<"$ADMIN_LIST" >&2
            echo "  Usage : sudo ./dev-deploy.sh --resetadmin <email>" >&2
            exit 1
        fi
        TARGET_EMAIL="$ADMIN_LIST"
    fi

    # La substitution de variable :'nom' de psql n'est appliquée qu'en mode
    # script (stdin/-f) — PAS avec -c, qui envoie la commande telle quelle
    # (vérifié empiriquement, contre-intuitif). D'où le `printf | psql`
    # plutôt que `psql -c` pour toute requête paramétrée ci-dessous.
    local EXISTS
    EXISTS="$(printf '%s\n' "SELECT 1 FROM app_user WHERE email = :'email';" \
        | docker compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U docflow -d docflow -v email="$TARGET_EMAIL" -tA)"
    if [[ -z "$EXISTS" ]]; then
        echo "ERREUR : aucun compte avec l'email '${TARGET_EMAIL}'." >&2
        exit 1
    fi

    local NEW_PASSWORD NEW_HASH
    NEW_PASSWORD="$(python3 -c \
        "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(20)))")"

    # Hash calculé DANS le container app : garantit la même version
    # d'argon2-cffi que celle utilisée par l'application elle-même. Le mot
    # de passe transite par stdin, jamais en argv (évite qu'il apparaisse
    # dans une liste de process).
    NEW_HASH="$(printf '%s' "$NEW_PASSWORD" | docker compose -f "$COMPOSE_FILE" exec -T app \
        python3 -c "import sys; from argon2 import PasswordHasher; print(PasswordHasher().hash(sys.stdin.read()))")"

    printf '%s\n' "UPDATE app_user SET password_hash = :'hash' WHERE email = :'email';" \
        | docker compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U docflow -d docflow -v email="$TARGET_EMAIL" -v hash="$NEW_HASH" \
        || { echo "ERREUR : la mise à jour en base a échoué." >&2; exit 1; }

    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""
    echo "  ✓ Mot de passe réinitialisé"
    echo ""
    echo "  Email        : ${TARGET_EMAIL}"
    echo "  Mot de passe : ${NEW_PASSWORD}"
    echo ""
    echo "  À noter immédiatement — non ré-affiché, non stocké par ce script."
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
}

main "$@"
