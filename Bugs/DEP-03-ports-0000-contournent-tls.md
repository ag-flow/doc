# DEP-03 — Ports publiés sur `0.0.0.0` contournant le TLS

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : déploiement / réseau
- **Fichiers** : `deploy/docker-compose.yml:9-10` ; `deploy/docker-compose.prod.yml:6-7`

## Description

`ports: - "8080:8080"` publie sur **toutes** les interfaces. `DEPLOY.md` prescrit Caddy/Nginx en frontal sur le même hôte via `localhost:8080` — mais l'app reste joignable **en HTTP direct depuis l'extérieur** sur `:8080`, contournant le TLS. (Docker contourne en plus ufw/iptables INPUT via ses règles NAT.)

## Scénario de reproduction

1. Prod avec Caddy en HTTPS.
2. Un client externe tape `http://serveur:8080`.
3. Trafic authentifié (JWT) transmis en clair, hors du reverse proxy TLS.

## Impact

Le TLS peut être contourné ; les JWT circulent en clair pour qui vise le port direct.

## Piste de correction

`"127.0.0.1:8080:8080"` dans les deux fichiers compose (le proxy accède via localhost, conformément à la doc).
