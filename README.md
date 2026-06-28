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
cd backend && uv run uvicorn docflow.app:app --reload   # :8080

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
