# Repères du dépôt — commandes et layout

> Fragment déclenché — texte intégral déplacé depuis `CLAUDE.md` le 2026-09-27
> (remise en forme sous le quota idéal). L'invariant est en synthèse dans
> `CLAUDE.md` ; le détail est ici, au mot près.

## Commandes essentielles

Les six fonctions, back et front. Détail et pièges : fragments de technologie.

```bash
# Installer          cd backend && uv sync          | cd frontend && npm install
# Lancer en local    uv run uvicorn docflow.app:app --reload  (:8000) | npm run dev (:5173)
# Tester             cd backend && uv run pytest -v | cd frontend && npm run test
# Style              cd backend && uv run ruff check src/ tests/      (pas d'ESLint côté front)
# Types              cd backend && uv run mypy src/ | cd frontend && npx tsc -b
# Construire         cd frontend && npm run build
# Migrations         cd backend && uv run python -m docflow.db.apply  (idempotent)
# Stack locale       docker compose -f deploy/docker-compose.yml up -d
```

**Pas de linter JS configuré** : `tsc -b` et Vitest sont les garde-fous côté
front. N'invoque pas `eslint`, il n'a pas de configuration ici.

## Layout du code

```
backend/migrations/        un .sql numéroté IMMUABLE par migration
backend/src/docflow/       app.py (FastAPI + lifespan : pool asyncpg, apply au boot)
  config/ db/ secrets/     env · pool + runner · résolveur ${vault://…}
  auth/ oidc/              bootstrap admin argon2 → JWT, RBAC, anti-lock-out
  workspaces/ types/ properties/ documents/ blocks/
  codecs/                  registre de types de contenu (parse/serialize/validate)
  mcp/ schemas/            serveur MCP · DTOs API pydantic
frontend/src/              components/ pages/ hooks/ contexts/ locales/ styles/
  lib/contentSurfaces/     registre de surfaces — miroir front des codecs
  lib/canvas/ lib/mld/     canvas de diagramme · adaptateur modèle de données
  test/                    Vitest + React Testing Library
deploy/                    Dockerfile (AUCUN secret) · compose dev & prod · DEPLOY.md
dev-deploy.sh · specs/ · LESSONS.md · ia_instructions/ · CLAUDE.md
```
