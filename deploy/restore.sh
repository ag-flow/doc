#!/usr/bin/env bash
# restore.sh — Restauration d'un dump docflow (pg_dump --format=custom).
# À exécuter sur la VM, en root, depuis /opt/docflow :
#   sudo ./deploy/restore.sh /data/backups/docflow_all_….dump [OPTIONS]
#
# Couvre les deux cas de DEPLOY.md § Restauration :
#   - par-dessus une instance existante : rien d'autre à fournir ;
#   - serveur tout neuf : passer --key pour reporter ENCRYPTION_KEY et
#     JWT_SECRET de l'ancienne instance dans /data/.env AVANT le restore
#     (fichier .key déposé par le job dump à côté de l'archive). Un
#     <archive>.key posé à côté du .dump est détecté automatiquement.
#
# Le script : vérifie l'archive, reporte les clés (.env sauvegardé en
# .env.bak.<ts>, DATABASE_URL jamais touché), arrête l'app, restaure
# (--clean --if-exists --no-owner --exit-on-error), et ne redémarre l'app
# (--force-recreate, pour relire /data/.env) que si pg_restore sort en 0.
#
# Options :
#   --key FICHIER    fichier .key (matériel de restauration) à reporter
#   --compose FICHIER  compose à utiliser (défaut : auto-détection)
#   --yes            saute la confirmation (scripts) — sinon taper RESTORE

set -euo pipefail
IFS=$'\n\t'

ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
err() { printf '  \033[31m✗ %s\033[0m\n' "$*" >&2; }

main() {
    local APP_DIR="${APP_DIR:-/opt/docflow}"
    local ENV_FILE="${DATA_ROOT:-/data}/.env"
    local DUMP_FILE="" KEY_FILE="" COMPOSE_FILE="" ASSUME_YES=0

    # ─── Arguments ────────────────────────────────────────────────────────────
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --key)     KEY_FILE="${2:?--key exige un fichier}"; shift 2 ;;
            --compose) COMPOSE_FILE="${2:?--compose exige un fichier}"; shift 2 ;;
            --yes)     ASSUME_YES=1; shift ;;
            --*)       err "flag inconnu : $1"; exit 1 ;;
            *)
                if [[ -n "$DUMP_FILE" ]]; then err "un seul fichier dump attendu"; exit 1; fi
                DUMP_FILE="$1"; shift ;;
        esac
    done
    if [[ -z "$DUMP_FILE" ]]; then
        err "usage : sudo ./deploy/restore.sh ARCHIVE.dump [--key ARCHIVE.key] [--compose FICHIER] [--yes]"
        exit 1
    fi
    [[ -f "$DUMP_FILE" ]] || { err "archive introuvable : $DUMP_FILE"; exit 1; }

    # .key auto-détecté à côté de l'archive si non fourni
    if [[ -z "$KEY_FILE" && -f "${DUMP_FILE%.dump}.key" ]]; then
        KEY_FILE="${DUMP_FILE%.dump}.key"
        ok "fichier de clés détecté : $KEY_FILE"
    fi
    [[ -z "$KEY_FILE" || -f "$KEY_FILE" ]] || { err "fichier .key introuvable : $KEY_FILE"; exit 1; }

    # Compose : auto-détection prod puis dev
    cd "$APP_DIR"
    if [[ -z "$COMPOSE_FILE" ]]; then
        if [[ -f docker-compose.prod.yml ]]; then COMPOSE_FILE="docker-compose.prod.yml"
        elif [[ -f deploy/docker-compose.yml ]]; then COMPOSE_FILE="deploy/docker-compose.yml"
        else err "aucun compose trouvé (docker-compose.prod.yml ni deploy/docker-compose.yml)"; exit 1
        fi
    fi
    [[ -f "$COMPOSE_FILE" ]] || { err "compose introuvable : $COMPOSE_FILE"; exit 1; }
    [[ -f "$ENV_FILE" ]] || { err "$ENV_FILE absent — lancer d'abord l'installation (l'app doit avoir été provisionnée)"; exit 1; }
    ok "compose : $COMPOSE_FILE"

    # ─── Confirmation (destructif) ────────────────────────────────────────────
    echo
    echo "  La restauration ÉCRASE le contenu actuel de la base avec :"
    echo "    $DUMP_FILE"
    [[ -n "$KEY_FILE" ]] && echo "  et reporte ENCRYPTION_KEY / JWT_SECRET depuis : $KEY_FILE"
    if [[ "$ASSUME_YES" -ne 1 ]]; then
        printf '  Taper RESTORE pour confirmer : '
        local answer; read -r answer
        [[ "$answer" == "RESTORE" ]] || { err "annulé"; exit 1; }
    fi

    # ─── 1. Report des clés de l'ancienne instance (avant tout démarrage) ────
    if [[ -n "$KEY_FILE" ]]; then
        local enc jwt
        enc="$(grep -E '^ENCRYPTION_KEY=' "$KEY_FILE" | head -1 | cut -d= -f2- || true)"
        jwt="$(grep -E '^JWT_SECRET='     "$KEY_FILE" | head -1 | cut -d= -f2- || true)"
        [[ -n "$enc" ]] || { err "ENCRYPTION_KEY absent de $KEY_FILE"; exit 1; }
        cp -a "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
        # DATABASE_URL n'est JAMAIS touché : il correspond au Postgres local.
        sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${enc}|" "$ENV_FILE"
        if [[ -n "$jwt" ]]; then
            sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${jwt}|" "$ENV_FILE"
        fi
        ok "ENCRYPTION_KEY${jwt:+ et JWT_SECRET} reportés dans $ENV_FILE (backup .bak conservé)"
    fi

    # ─── 2. App arrêtée, Postgres seul ────────────────────────────────────────
    echo "==> Arrêt de l'app, démarrage de Postgres…"
    docker compose -f "$COMPOSE_FILE" stop app
    docker compose -f "$COMPOSE_FILE" up -d postgres
    # attendre le healthcheck postgres
    local i
    for i in $(seq 1 30); do
        if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U docflow -d docflow >/dev/null 2>&1; then
            break
        fi
        sleep 2
        [[ "$i" -eq 30 ]] && { err "Postgres injoignable après 60 s"; exit 1; }
    done
    ok "Postgres prêt"

    # ─── 3. Restauration ─────────────────────────────────────────────────────
    echo "==> pg_restore (--clean --if-exists --no-owner --exit-on-error)…"
    if ! docker compose -f "$COMPOSE_FILE" exec -T postgres \
        pg_restore -U docflow -d docflow --clean --if-exists --no-owner --exit-on-error \
        < "$DUMP_FILE"; then
        err "pg_restore a échoué — l'app reste ARRÊTÉE (base possiblement incomplète)."
        err "Corriger puis relancer ce script ; ne redémarrer l'app qu'après un restore en 0."
        exit 1
    fi
    ok "restauration terminée (code 0)"

    # ─── 4. Redémarrage de l'app (relit /data/.env) ──────────────────────────
    echo "==> Redémarrage de l'app…"
    docker compose -f "$COMPOSE_FILE" up -d --force-recreate app
    for i in $(seq 1 30); do
        if curl -sf http://localhost:8080/health >/dev/null 2>&1; then
            ok "app démarrée (health OK) — les migrations manquantes ont été rejouées au boot"
            echo
            echo "  Vérifications à faire maintenant (DEPLOY.md § Restauration) :"
            echo "   1. connexion avec un compte d'avant le sinistre ;"
            echo "   2. workspaces/documents présents ;"
            echo "   3. « Tester » sur chaque remote point (valide ENCRYPTION_KEY) ;"
            echo "   4. un run de backup manuel."
            return 0
        fi
        sleep 2
    done
    err "l'app ne répond pas sur /health après 60 s — voir : docker compose -f $COMPOSE_FILE logs app"
    exit 1
}

main "$@"
