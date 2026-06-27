#!/usr/bin/env bash
# prod-deploy.sh — déploiement production docflow
#
# Première installation :
#   curl -fsSL https://raw.githubusercontent.com/ag-flow/doc/main/deploy/prod-deploy.sh -o prod-deploy.sh
#   bash prod-deploy.sh
#
# Mise à jour :
#   bash /opt/docflow/prod-deploy.sh

set -euo pipefail

IMAGE="ghcr.io/ag-flow/doc:latest"
WORKDIR="/opt/docflow"
DATA="/data"
COMPOSE_URL="https://raw.githubusercontent.com/ag-flow/doc/main/deploy/docker-compose.prod.yml"
ENV_EXAMPLE_URL="https://raw.githubusercontent.com/ag-flow/doc/main/deploy/.env.example"
COMPOSE="$WORKDIR/docker-compose.prod.yml"

# ── Couleurs ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
die()  { echo -e "${RED}✗${NC} $*" >&2; exit 1; }

echo ""
echo "══════════════════════════════════════════"
echo "  docflow — déploiement production"
echo "══════════════════════════════════════════"
echo ""

# ── Prérequis ─────────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "Docker n'est pas installé."
docker compose version >/dev/null 2>&1 || die "Le plugin Docker Compose n'est pas installé."

# ── Répertoires ───────────────────────────────────────────────────────────────
mkdir -p "$WORKDIR" "$DATA"
chmod 700 "$DATA"

# ── Télécharger docker-compose.prod.yml (toujours la dernière version) ────────
echo "Téléchargement du fichier Compose…"
curl -fsSL "$COMPOSE_URL" -o "$COMPOSE" || die "Impossible de télécharger docker-compose.prod.yml"
ok "docker-compose.prod.yml mis à jour"

# ── Première installation : configurer /data ───────────────────────────────────
FIRST_RUN=false
if [[ ! -f "$DATA/.env" ]]; then
    FIRST_RUN=true
    warn "Première installation détectée."
    echo ""

    # Mot de passe Postgres
    PG_PASS=$(python3 -c "import secrets; print(secrets.token_hex(24))")
    echo "$PG_PASS" > "$DATA/pg_password.txt"
    chmod 600 "$DATA/pg_password.txt"
    ok "Mot de passe PostgreSQL généré → $DATA/pg_password.txt"

    # Générer les secrets
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    ENCRYPTION_KEY=$(python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")

    # Télécharger et pré-remplir .env
    curl -fsSL "$ENV_EXAMPLE_URL" -o "$DATA/.env" || die "Impossible de télécharger .env.example"
    chmod 600 "$DATA/.env"

    # Substituer les valeurs générées automatiquement
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql://docflow:${PG_PASS}@postgres:5432/docflow|" "$DATA/.env"
    sed -i "s|JWT_SECRET=.*|JWT_SECRET=${JWT_SECRET}|" "$DATA/.env"
    sed -i "s|ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${ENCRYPTION_KEY}|" "$DATA/.env"

    ok "Fichier $DATA/.env créé avec JWT_SECRET et ENCRYPTION_KEY pré-remplis"
    echo ""
    echo -e "${YELLOW}ACTION REQUISE${NC} — Éditer $DATA/.env et renseigner :"
    echo "   ADMIN_EMAIL=<votre email>"
    echo "   ADMIN_PASSWORD=<mot de passe fort>"
    echo ""
    echo "   nano $DATA/.env"
    echo ""
    read -r -p "Appuyer sur Entrée une fois .env complété…"
fi

# ── Vérifier que les variables obligatoires sont renseignées ───────────────────
source "$DATA/.env" 2>/dev/null || true
: "${DATABASE_URL:?'DATABASE_URL manquant dans $DATA/.env'}"
: "${JWT_SECRET:?'JWT_SECRET manquant dans $DATA/.env'}"
: "${ADMIN_EMAIL:?'ADMIN_EMAIL manquant dans $DATA/.env'}"
: "${ADMIN_PASSWORD:?'ADMIN_PASSWORD manquant dans $DATA/.env'}"
: "${ENCRYPTION_KEY:?'ENCRYPTION_KEY manquant dans $DATA/.env'}"
ok "Configuration validée"

# ── Tirer l'image ──────────────────────────────────────────────────────────────
echo "Téléchargement de l'image $IMAGE…"
docker pull "$IMAGE" || die "Échec du pull. Vérifier l'accès à GHCR (voir DEPLOY.md § Étape 2)."
ok "Image à jour"

# ── Démarrer (ou redémarrer) ───────────────────────────────────────────────────
if docker compose -f "$COMPOSE" ps --quiet app 2>/dev/null | grep -q .; then
    echo "Redémarrage du conteneur app…"
    docker compose -f "$COMPOSE" up -d --no-deps app
else
    echo "Démarrage de la stack…"
    docker compose -f "$COMPOSE" up -d
fi
ok "Stack démarrée"

# ── Smoke test ────────────────────────────────────────────────────────────────
echo "Attente du démarrage (max 60 s)…"
for i in $(seq 1 20); do
    if curl -sf http://localhost:8080/health >/dev/null 2>&1; then
        echo ""
        ok "docflow est opérationnel → http://localhost:8080"
        echo ""
        exit 0
    fi
    sleep 3
done

die "Timeout — docflow ne répond pas. Consulter les logs :
  docker compose -f $COMPOSE logs app"
