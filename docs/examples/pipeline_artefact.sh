#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Exemple de pipeline « artefact » de bout en bout (fiche c50291e7).
#
# Illustre le BESOIN FINAL : produire un fichier, le pousser dans docflow, puis
# l'attacher à un document sous forme de PUCE téléchargeable. Ce script est la
# part docflow du besoin ; le déclenchement automatique (règle workflow qui
# appelle ce pipeline sur un événement) vit dans ag.flow, HORS de ce dépôt.
#
# Chaîne :
#   1. upload de l'artefact         → POST /artifacts            (id)
#   2. ajout du fragment en pied    → POST /documents/{id}/append (puce)
#   3. (option) lien signé          → GET  /artifacts/{id}/link   (URL courte)
#
# Prérequis : un workspace, un bloc et un document existants. Adapter les
# variables ci-dessous. Dépendances : curl, python3.
# ─────────────────────────────────────────────────────────────────────────────
set -eu

B=${DOCFLOW_API:-http://localhost:8000/api}
EMAIL=${DOCFLOW_EMAIL:-claire@exemple.fr}
PASSWORD=${DOCFLOW_PASSWORD:-Docflow-Demo-2026!}
WS=${DOCFLOW_WS:-produit-alpha}
BLOCK=${DOCFLOW_BLOCK:-wiki}

TOKEN=$(curl -s -X POST "$B/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"
jget() { python3 -c "import sys,json;print(json.load(sys.stdin)[\"$1\"])"; }

# ── 0. Document porteur ──────────────────────────────────────────────────────
# On crée un document simple pour la démonstration (dans un cas réel, il existe
# déjà : passer directement son doc_technical_key). La création REST attend le
# block_id (UUID) — on le résout depuis le slug du bloc.
echo "== document porteur =="
BLOCK_ID=$(curl -s "$B/workspaces/$WS/blocks" -H "$AUTH" \
  | python3 -c "import sys,json;print(next(b['id'] for b in json.load(sys.stdin) if b['slug']=='$BLOCK'))")
DOC=$(curl -s -X POST "$B/workspaces/$WS/documents" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"title\":\"Rapport hebdomadaire\",\"block_id\":\"$BLOCK_ID\",\"content\":\"# Rapport hebdomadaire\\n\\nSynthèse de la semaine.\"}" \
  | jget doc_technical_key)
echo "doc_id=$DOC"

# ── 1. Produire puis pousser l'artefact ──────────────────────────────────────
# Ici un PDF minimal généré à la volée ; en pratique, le fichier vient du job
# amont (export, capture, archive…).
echo "== upload artefact =="
TMP=$(mktemp --suffix=.pdf)
printf '%%PDF-1.7\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%%%EOF\n' > "$TMP"
ART=$(curl -s -X POST "$B/workspaces/$WS/artifacts" -H "$AUTH" \
  -F "file=@$TMP;filename=rapport-s30.pdf" \
  | jget id)
rm -f "$TMP"
echo "artifact_id=$ART"

# ── 2. Attacher l'artefact au document en PUCE ───────────────────────────────
# La forme `[libellé](artifact://<id>)` SEULE sur sa ligne devient une puce
# téléchargeable. On l'ajoute en pied via l'endpoint append (positionnement
# littéral, pas de gestion de version côté appelant).
echo "== append de la puce =="
curl -s -X POST "$B/workspaces/$WS/documents/$DOC/append" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"content\":\"[Rapport S30 (PDF)](artifact://$ART)\",\"position\":\"bottom\"}" \
  | jget version | xargs echo "nouvelle version ="

# ── 3. (Option) lien signé de partage court ──────────────────────────────────
echo "== lien signé =="
curl -s "$B/workspaces/$WS/artifacts/$ART/link" -H "$AUTH"
echo

echo "✅ Terminé : ouvrir le document « Rapport hebdomadaire » — la puce fichier"
echo "   s'affiche en pied, avec Télécharger et Ouvrir."
