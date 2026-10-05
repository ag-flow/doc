# docflow

Application self-hosted de **gestion documentaire et de structures de données personnalisables**, organisée par workspace.

- Pages markdown arborescentes avec éditeur riche
- Types fonctionnels définis par l'utilisateur (epic ⊃ feature ⊃ tâche…) avec propriétés typées
- Statuts = propriété `restricted_list` (aucun concept câblé en dur)
- Auth bootstrap admin local (break-glass permanent) + OIDC Keycloak
- Export Markdown/Obsidian, vues sauvegardées, automates HTTP, webhooks
- Serveur MCP exposant le store

## Stack

| Couche | Technologies |
|--------|-------------|
| Backend | Python 3.12 · FastAPI · asyncpg · pydantic v2 · argon2-cffi · structlog |
| Base de données | PostgreSQL 13+ · migrations versionnées · apply idempotent |
| Auth | JWT · OIDC Keycloak · Harpocrate (secrets vault) |
| Frontend | Vite · React · TypeScript strict · TanStack Query · Tailwind · shadcn/ui |

## Démarrage rapide (développement)

```bash
# Backend
cd backend && uv sync
cd backend && uv run uvicorn docflow.app:app --reload   # :8000

# Migrations (applique les .sql manquants dans l'ordre)
cd backend && uv run python -m docflow.db.apply

# Frontend
cd frontend && npm install && npm run dev               # :5173

# Stack locale complète (app + postgres)
docker compose -f deploy/docker-compose.yml up -d
```

## Déploiement en production

Voir [deploy/DEPLOY.md](deploy/DEPLOY.md).

## Documentation

| Document | Contenu |
|----------|---------|
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | Guide de démarrage pour les nouveaux utilisateurs |
| [docs/FONCTIONNALITES.md](docs/FONCTIONNALITES.md) | Référence complète de toutes les fonctionnalités |
| [deploy/DEPLOY.md](deploy/DEPLOY.md) | Installation et mise à jour en production |
| [specs/00_README.md](specs/00_README.md) | Corpus de spécifications techniques |
| [LESSONS.md](LESSONS.md) | Leçons apprises (auto-améliorations) |

## Variables d'environnement essentielles

Copiez `scripts/.env.example` vers `/data/.env` et renseignez :

```
DATABASE_URL=postgresql://docflow:PASSWORD@localhost:5432/docflow
JWT_SECRET=<secret aléatoire ≥ 32 caractères>
ENCRYPTION_KEY=<clé Fernet base64>
HARPOCRATE_URL=https://vault.yoops.org   # optionnel, pour les secrets vault
LOG_LEVEL=INFO
```

Le premier compte admin est créé via le wizard in-app (POST /api/setup/init-admin) au premier démarrage.

## Licence

docflow est distribué sous la **Functional Source License, Version 1.1, Apache 2.0
Future License** — identifiant SPDX **`FSL-1.1-ALv2`**. Texte intégral :
[LICENSE](LICENSE) ; mentions tierces : [NOTICE](NOTICE).

C'est une licence **source-available** : le code est ouvert et librement
utilisable, à la seule exception d'un usage concurrent, et chaque version
**bascule automatiquement sous Apache 2.0 deux ans** après sa mise à disposition.

| Usage | Autorisé |
|-------|:--------:|
| Usage interne (entreprise, perso), auto-hébergement | ✅ |
| Lire, modifier, forker, redistribuer le code | ✅ |
| Recherche et enseignement non commerciaux | ✅ |
| Services professionnels rendus à un utilisateur légitime de docflow | ✅ |
| Revendre docflow, ou en faire un produit/SaaS concurrent | ❌ |
| Offrir un service qui s'y substitue ou en reproduit la fonctionnalité | ❌ |

Deux ans après la publication d'une version donnée, ces restrictions tombent :
cette version devient utilisable sous **Apache License 2.0**, sans réserve.

Le résumé ci-dessus est indicatif ; seul le fichier [LICENSE](LICENSE) fait foi.
FAQ officielle de la licence : <https://fsl.software>.

Toute contribution est acceptée selon les termes décrits dans
[CONTRIBUTING.md](CONTRIBUTING.md).
