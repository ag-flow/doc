# docflow — Corpus de specs

> Nom de travail : **docflow** (à renommer). Projet **indépendant** d'ag.flow / devpod-ui.

## Objectif

Application self-hosted de gestion documentaire et de structures de données **personnalisables par workspace** : pages markdown arborescentes + types fonctionnels définis par l'utilisateur (epic ⊃ feature) + propriétés typées (`text`/`int`/`restricted_list`) dont le statut, le tout exposé à terme via un serveur **MCP** de première classe. Auth bootstrap admin local puis OIDC Keycloak.

## Principes non négociables

1. **Une seule base PostgreSQL**, deux plans logiques : *instance* (admin, OIDC — transverse) et *contenu* (scoped workspace via `workspace_technical_key` sur chaque ligne). Voir `01_ARCHITECTURE.md`.
2. **Schéma-as-code.** Le schéma vit en migrations git, appliqué par une primitive `apply` idempotente. Réconciliation **additive** ; destructif = explicite.
3. **Aucun secret en clair** — ni `.env` commité, ni log, ni colonne. Secrets via `${vault://...}` Harpocrate.
4. **Bootstrap admin = break-glass permanent.** On ne configure pas OIDC via OIDC ; un admin local par mot de passe préexiste toujours et reste connectable.
5. **Le slug est la clé fonctionnelle stable** ; le label est affichable et renommable. Le code et les templates pointent le slug, jamais le label.
6. **Le statut n'est pas un concept câblé** : c'est une propriété `restricted_list`. Aucune table « status » dédiée.

## Comment Claude Code doit utiliser ce corpus

- Lire **`CLAUDE.md` (racine) en premier** (autonomie, conventions, DoD).
- Puis `01_ARCHITECTURE.md`, `02_DATA_MODEL.md`, `03_PITFALLS.md` (contexte transversal — `03` contient des **exigences**).
- Exécuter les milestones **dans l'ordre** `10_M1` → `19_M9`. Chaque milestone est livrable et testable indépendamment. Ne pas démarrer un milestone sans avoir validé la DoD du précédent.
- Avant tout code utilisant une lib externe (FastAPI, asyncpg, authlib, SDK MCP…), **consulter Context7** : les API dérivent, le corpus décrit l'intention.

## Ordre des milestones

| #  | Fichier                       | Contenu                                                                                  | Dépend de |
| -- | ----------------------------- | ---------------------------------------------------------------------------------------- | --------- |
| M1 | `10_M1_foundation.md`         | Squelette, config pydantic-settings, pool asyncpg, runner `apply` + `0001_init.sql`, résolveur secrets `${vault://}` | —         |
| M2 | `11_M2_bootstrap_auth.md`     | Seed bootstrap admin depuis l'env, login local argon2 → JWT, RBAC, garde-fou anti-lock-out | M1        |
| M3 | `12_M3_types_statuts.md`      | CRUD `functional_type` (hiérarchie, scope workspace), statuts via `properties_defs` restricted_list + `properties_allowed_values` — **surface de l'écran prioritaire** | M1, M2    |
| M4 | `13_M4_workspaces_docs.md`    | CRUD `workspace`, documents arborescents (parent, contenu md, type)                       | M1, M2    |
| M5 | `14_M5_props_values.md`       | Propriétés génériques `text`/`int`/`restricted_list`, `constraints` (min/max/pattern + message), `properties_values` sur documents, validation applicative | M3, M4    |
| M6 | `15_M6_data_blocks.md`        | `data_block` arborescent, contrainte de type **miroir** (epic ⊃ feature), dénormalisation | M3, M4    |
| M7 | `16_M7_frontend.md`           | Écran admin (login + types & statuts) câblé à l'API, puis arbre documents                 | M2, M3, M4 |
| M8 | `17_M8_oidc.md`               | Config OIDC saisie par le bootstrap admin, provisioning à la volée, break-glass préservé  | M2        |
| M9 | `19_M9_mcp.md`                | Serveur MCP exposant le store en lecture/écriture sous RBAC, namespace par workspace      | M3→M6     |

> Les fichiers `11`→`19` sont détaillés **au fur et à mesure** qu'on atteint le milestone (workflow gaté par DoD). `10_M1` est fourni complet pour démarrer.

## Stack imposée

- Python 3.12, FastAPI, pydantic v2 + pydantic-settings, asyncpg, authlib (OIDC), httpx, structlog, argon2-cffi, uvicorn. Tests : pytest + pytest-asyncio.
- PostgreSQL 13+ (`gen_random_uuid()` natif).
- Frontend : Vite + React + TypeScript + TanStack Query + Tailwind + shadcn/ui + i18next + Vitest.
- Keycloak (`security.yoops.org`, realm `yoops`) — déjà déployé.
- Harpocrate (`harpocrate.yoops.org`) — résolution `${vault://...}`, fallback inline.
