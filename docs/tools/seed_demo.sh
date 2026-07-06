#!/bin/bash
# Données de démo pour les screenshots de la doc utilisateur.
set -eu
B=http://192.168.10.197:18086/api

curl -s -X POST $B/setup/init-admin -H 'Content-Type: application/json' \
  -d '{"username":"claire","email":"claire@exemple.fr","password":"Docflow-Demo-2026!"}' >/dev/null || true
TOKEN=$(curl -s -X POST $B/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"claire@exemple.fr","password":"Docflow-Demo-2026!"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"
J='Content-Type: application/json'

post() { curl -s -X POST "$B$1" -H "$AUTH" -H "$J" -d "$2"; }
patch() { curl -s -X PATCH "$B$1" -H "$AUTH" -H "$J" -d "$2"; }
put() { curl -s -X PUT "$B$1" -H "$AUTH" -H "$J" -d "$2"; }

echo "== workspace =="
post /workspaces '{"slug":"produit-alpha","label":"Produit Alpha","description":"Documentation et roadmap du produit Alpha"}' >/dev/null

echo "== types =="
post /workspaces/produit-alpha/types '{"slug":"epic","label":"Épic"}' >/dev/null
post /workspaces/produit-alpha/types '{"slug":"feature","label":"Fonctionnalité","parent_slug":"epic"}' >/dev/null
post /workspaces/produit-alpha/types '{"slug":"page","label":"Page"}' >/dev/null

echo "== propriétés feature : statut + estimation =="
post /workspaces/produit-alpha/types/feature/properties '{"slug":"statut","label":"Statut","type":"restricted_list","required":true}' >/dev/null
P=/workspaces/produit-alpha/types/feature/properties/statut/values
post $P '{"slug":"a-faire","label":"À faire","position":0,"color":"#9ca3af"}' >/dev/null
post $P '{"slug":"en-cours","label":"En cours","position":1,"color":"#3b82f6"}' >/dev/null
post $P '{"slug":"termine","label":"Terminé","position":2,"color":"#22c55e"}' >/dev/null
post /workspaces/produit-alpha/types/feature/properties '{"slug":"estimation","label":"Estimation (jours)","type":"int"}' >/dev/null

echo "== blocs =="
post /workspaces/produit-alpha/blocks '{"slug":"roadmap","label":"Roadmap","functional_type_slug":"epic"}' >/dev/null
post /workspaces/produit-alpha/blocks '{"slug":"wiki","label":"Wiki","functional_type_slug":"page"}' >/dev/null

doc_id() { python3 -c 'import sys,json;print(json.load(sys.stdin)["doc_technical_key"])'; }

echo "== roadmap : épics + fonctionnalités =="
E1=$(post /workspaces/produit-alpha/blocks/roadmap/documents \
  '{"title":"Authentification SSO","slug":"auth-sso","functional_type_slug":"epic"}' | doc_id)
patch /workspaces/produit-alpha/documents/$E1 \
  '{"content":"## Objectif\n\nPermettre aux utilisateurs de se connecter avec le compte d'"'"'entreprise (Keycloak), sans créer un mot de passe de plus.\n\n## Périmètre\n\n- Connexion OIDC\n- Compte de secours local pour les admins\n- Création du compte à la première connexion","expected_version":1}' >/dev/null

F1=$(post /workspaces/produit-alpha/blocks/roadmap/documents \
  "{\"title\":\"Connexion via Keycloak\",\"slug\":\"login-keycloak\",\"functional_type_slug\":\"feature\",\"parent_id\":\"$E1\",\"properties\":{\"statut\":\"en-cours\",\"estimation\":\"5\"}}" | doc_id)
patch /workspaces/produit-alpha/documents/$F1 \
  '{"content":"## Description\n\nL'"'"'utilisateur clique sur « Se connecter avec Keycloak », s'"'"'authentifie sur le serveur d'"'"'entreprise et revient connecté.\n\n## Critères d'"'"'acceptation\n\n- Le bouton n'"'"'apparaît que si OIDC est configuré\n- Un compte est créé automatiquement à la première connexion\n- Le compte doit être validé par un admin avant d'"'"'accéder au contenu","expected_version":1}' >/dev/null

F2=$(post /workspaces/produit-alpha/blocks/roadmap/documents \
  "{\"title\":\"Compte de secours local\",\"slug\":\"break-glass\",\"functional_type_slug\":\"feature\",\"parent_id\":\"$E1\",\"properties\":{\"statut\":\"termine\",\"estimation\":\"2\"}}" | doc_id)

post /workspaces/produit-alpha/blocks/roadmap/documents \
  "{\"title\":\"Provisioning à la volée\",\"slug\":\"provisioning\",\"functional_type_slug\":\"feature\",\"parent_id\":\"$E1\",\"properties\":{\"statut\":\"a-faire\",\"estimation\":\"3\"}}" >/dev/null

E2=$(post /workspaces/produit-alpha/blocks/roadmap/documents \
  '{"title":"Recherche plein texte","slug":"recherche","functional_type_slug":"epic"}' | doc_id)
post /workspaces/produit-alpha/blocks/roadmap/documents \
  "{\"title\":\"Indexation des documents\",\"slug\":\"indexation\",\"functional_type_slug\":\"feature\",\"parent_id\":\"$E2\",\"properties\":{\"statut\":\"a-faire\",\"estimation\":\"8\"}}" >/dev/null

echo "== wiki : guide (exposé) + architecture =="
G1=$(post /workspaces/produit-alpha/blocks/wiki/documents \
  '{"title":"Guide d'"'"'installation","slug":"guide-installation","functional_type_slug":"page"}' | doc_id)
patch /workspaces/produit-alpha/documents/$G1 \
  '{"content":"## Prérequis\n\n- Docker et docker compose\n- Un serveur Linux avec 2 Go de RAM\n\n## Installation\n\n1. Cloner le dépôt sur le serveur\n2. Copier `deploy/.env.example` vers `/data/.env`\n3. Lancer `docker compose -f deploy/docker-compose.yml up -d`\n4. Ouvrir `http://votre-serveur:8080` et créer le compte administrateur\n\n## Vérification\n\nLa commande suivante doit répondre `ok` :\n\n```bash\ncurl http://votre-serveur:8080/health\n```","expected_version":1}' >/dev/null
patch /workspaces/produit-alpha/documents/$G1/exposed '{"exposed":true}' >/dev/null

A1=$(post /workspaces/produit-alpha/blocks/wiki/documents \
  '{"title":"Architecture","slug":"architecture","functional_type_slug":"page"}' | doc_id)

echo "== upload du schéma + contenu Architecture =="
AID=$(curl -s -X POST $B/workspaces/produit-alpha/artifacts -H "$AUTH" \
  -F "file=@shots/architecture-demo.png;filename=architecture.png" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
patch /workspaces/produit-alpha/documents/$A1 \
  "{\"content\":\"## Vue d'ensemble\n\nL'application est un serveur unique devant une base PostgreSQL. Le frontend est servi par le backend, il n'y a qu'un seul port à exposer.\n\n![Schéma d'architecture](/api/workspaces/produit-alpha/artifacts/$AID)\n\n## À lire ensuite\n\n[Guide d'installation](docflow://doc/$G1)\",\"expected_version\":1}" >/dev/null

echo "DEMO_FEATURE_DOC=$F1"
echo "DEMO_ARCHI_DOC=$A1"
echo "DEMO_PUB_DOC=$G1"
