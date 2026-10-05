#!/usr/bin/env bash
# declarer-exposition.sh — déclare un service local auprès du registre du portail.
#
# Le service reçoit le nom `<workspace>-<service>` et devient joignable de
# l'extérieur par `https://<workspace>-<service>.<domaine>`, réservé à son
# propriétaire. Le visiteur ne désigne jamais une destination : il ne peut que
# nommer un service déjà déclaré ici (STANDARD « Exposer un service interne
# derrière l'authentification du portail »).
#
# Appelé par les scripts d'infra (dev-deploy.sh…) APRÈS un déploiement réussi.
#
# Contrat :
#   - PORTAL_TOKEN vient de l'ENVIRONNEMENT, jamais d'un argument : l'argv de
#     tout processus est lisible localement (`ps auxww`).
#   - Best-effort : sans jeton on passe son chemin sans bruit, et un portail
#     injoignable n'échoue PAS — la déclaration est idempotente et se rejoue au
#     prochain déploiement.
#
# Deux voies d'authentification, deux points d'entrée :
#   - défaut : PORTAL_TOKEN = jeton d'infra admin, endpoint /admin/expositions,
#     le propriétaire est DÉDUIT du workspace déclaré (voie de l'exploitant) ;
#   - --me    : PORTAL_TOKEN = code TOTP « <login>:<code> » obtenu via l'outil MCP
#     `totp_code` du portail, endpoint /me/expositions, le service est déclaré
#     SOUS le workspace de l'appelant authentifié (voie de l'agent, à privilégier
#     dans dev-deploy.sh).
#
# Usage :
#   PORTAL_TOKEN=... scripts/declarer-exposition.sh \
#       --portal https://dev.yoops.org --workspace docflow \
#       --service docflow --target-host 192.168.10.x --target-port 8080 \
#       [--host host-xxx] [--scheme http] [--path /vmui/] [--me]
#
#   --path : chemin d'entrée du service quand sa page ne vit pas sur `/`
#   (ex. /vmui/) — c'est ce que le lien de l'annuaire ouvrira.
set -euo pipefail

PORTAL_URL=""
WORKSPACE=""
SERVICE=""
TARGET_HOST=""
TARGET_PORT=""
HOST_NAME=""
SCHEME="http"
ENTRY_PATH=""
ENDPOINT="/admin/expositions"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --portal)      PORTAL_URL="$2";  shift 2 ;;
        --workspace)   WORKSPACE="$2";   shift 2 ;;
        --service)     SERVICE="$2";     shift 2 ;;
        --target-host) TARGET_HOST="$2"; shift 2 ;;
        --target-port) TARGET_PORT="$2"; shift 2 ;;
        --host)        HOST_NAME="$2";   shift 2 ;;
        --scheme)      SCHEME="$2";      shift 2 ;;
        --path)        ENTRY_PATH="$2";  shift 2 ;;
        --me)          ENDPOINT="/me/expositions"; shift ;;
        *) echo "Argument inconnu : $1" >&2; exit 2 ;;
    esac
done

# Pas de jeton = pas de portail à qui parler. Ce n'est pas une erreur : une
# stack peut être déployée hors de tout contexte portail.
if [[ -z "${PORTAL_TOKEN:-}" || -z "$PORTAL_URL" ]]; then
    exit 0
fi

for _requis in WORKSPACE SERVICE TARGET_HOST TARGET_PORT; do
    if [[ -z "${!_requis}" ]]; then
        echo "AVERTISSEMENT : --${_requis,,} manquant — exposition non déclarée." >&2
        exit 0
    fi
done

CHARGE=$(printf '{"workspace":"%s","service":"%s","host":"%s","target_host":"%s","target_port":%d,"scheme":"%s","entry_path":"%s"}' \
    "$WORKSPACE" "$SERVICE" "$HOST_NAME" "$TARGET_HOST" "$TARGET_PORT" "$SCHEME" "$ENTRY_PATH")

# Le jeton descend par un fichier de config curl lu sur stdin (-K -), jamais en
# argv : l'argv d'un processus est lisible par n'importe qui sur la machine.
HTTP_CODE=$(curl -sS \
    -w "%{http_code}" \
    -o /dev/null \
    -X PUT \
    -H "Content-Type: application/json" \
    -d "$CHARGE" \
    "${PORTAL_URL%/}${ENDPOINT}" \
    -K - 2>/dev/null <<CURL_CFG || true
header = "Authorization: Bearer ${PORTAL_TOKEN}"
CURL_CFG
)

if [[ "$HTTP_CODE" == "200" ]]; then
    echo "    Service exposé : ${WORKSPACE}-${SERVICE} → ${TARGET_HOST}:${TARGET_PORT}"
else
    # Jamais bloquant : le déploiement a réussi, c'est la déclaration qui a raté.
    echo "AVERTISSEMENT : déclaration de ${WORKSPACE}-${SERVICE} refusée (HTTP ${HTTP_CODE:-000})." >&2
fi
exit 0
