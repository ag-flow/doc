# DEP-07 — Version de `pg_dump` non maîtrisée dans l'image (base flottante)

- **Gravité** : 🟡 MINEUR
- **Confiance** : moyenne
- **Zone** : déploiement / Docker
- **Fichiers** : `deploy/Dockerfile:14-20` vs `postgres:16-alpine` (compose)

## Description

`postgresql-client` vient des dépôts de la base `python:3.12-slim`, dont la version Debian **flotte**. Sur base trixie → client 17 (OK contre serveur 16). Sur base bookworm (ou cache de build ancien) → client **15**, et `pg_dump` **refuse** de dumper un serveur 16 (« server version mismatch ») : la feature backup interne échoue à 100 %. Le couple client/serveur n'est contraint nulle part.

## Impact

Selon la base Debian utilisée au build, les sauvegardes internes peuvent échouer systématiquement.

## Piste de correction

Installer `postgresql-client-16` depuis le dépôt PGDG (version explicite), ou pinner la base (`python:3.12-slim-trixie`) avec un commentaire liant la version client au tag `postgres:16`.
