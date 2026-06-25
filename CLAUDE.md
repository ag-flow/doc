# docflow — Instructions Claude Code

> Nom de travail : **docflow** (à renommer une fois le produit nommé). Domaine de travail : `docflow.yoops.org`.
> Projet **indépendant** d'ag.flow, ag.flow.docker et devpod-ui (aucun couplage runtime ni de source).

## Projet

Application self-hosted de **gestion documentaire et de structures de données personnalisables**, organisée par workspace :

- des **pages markdown arborescentes** (une page a 0..1 parent, 0..n enfants) ;
- des **types fonctionnels définis par l'utilisateur** (ex. epic ⊃ feature) — rien n'est câblé en dur ;
- des **propriétés typées** (`text` / `int` / `restricted_list`) attachées aux types ;
- un **statut** qui n'est qu'une propriété `restricted_list` (slug stable + label affichable + ordre) ;
- une **auth bootstrap admin local** (break-glass) puis **OIDC Keycloak** ;
- un **serveur MCP** exposant le store (milestone ultérieur), conçu comme interface de première classe.

Spec complète : `specs/00_README.md` → milestones. **Lire `01`, `02`, `03` avant tout code** ; `03_PITFALLS.md` contient des **exigences**, pas des conseils.

### ⚠ Divergence assumée vs devpod-ui

**Ce projet UTILISE une base de données (PostgreSQL).** C'est l'inverse du principe n°1 « pas de base de données » de devpod-ui, et c'est **délibéré** : des propriétés typées et un filtrage par statut exigent un moteur de requête. **Ne pas importer la règle no-DB du projet voisin.** Justification complète : `01_ARCHITECTURE.md`.

## Standard de qualité

Code propre et bien fait, jamais la rapidité au détriment de la rigueur. Pas de raccourcis, pas de « c'est pas grave », pas de « on simplifiera plus tard ». Chaque tâche est faite correctement ou pas du tout.

**Pas de quick-and-dirty, JAMAIS.** Quand tu présentes des options de design, ne propose PAS d'option « quick & dirty » / « hardcode » / « wire-it-up-and-clean-later ». On fait toujours propre. Si une tâche est déraisonnable (scope qui explose, dépendance hors d'atteinte, API qui n'existe pas dans la version installée), **alerte explicitement l'utilisateur** plutôt que de proposer un compromis dégradé. L'utilisateur préfère qu'on découpe le chantier et qu'on fasse correctement la part qu'on prend.

## Stack technique

- **Backend** : Python 3.12 + FastAPI + pydantic v2 / pydantic-settings + **asyncpg** + authlib (OIDC) + httpx + structlog JSON + pytest. Hash mot de passe : argon2 (`argon2-cffi`).
- **Persistance** : **PostgreSQL 13+**, une seule base, deux plans logiques (instance / contenu scoped workspace). Schéma **versionné en git** sous `backend/migrations/`, appliqué par une primitive **`apply` idempotente**. **Réconciliation additive** (ADD COLUMN nullable = automatique ; renommage/suppression = migration explicite et revue). Pas d'ORM lourd : requêtes asyncpg explicites, **toujours paramétrées** (`$1..$n`), jamais d'interpolation de chaîne.
- **Auth** : bootstrap admin local (seedé depuis l'env, break-glass permanent) puis OIDC Keycloak (`security.yoops.org`, realm `yoops`, client `docflow`). RBAC `admin` / `superadmin`.
- **Secrets** : Harpocrate via références `${vault://...}` ; **jamais en clair** (ni `.env` commité, ni log, ni colonne en clair). `client_secret` OIDC = référence vault.
- **Frontend** (quand l'UI démarre) : Vite + React + TypeScript strict + react-router-dom + TanStack Query + Tailwind + shadcn/ui + i18next + Vitest — mêmes conventions que les autres projets yoops.
- **MCP** : serveur MCP exposant le store en lecture/écriture sous le même RBAC (milestone ultérieur).

## Dev & cible

- **Développement** : local (uv + node), une instance Postgres de test.
- **Cible** : schéma dédié dans l'instance Postgres existante (celle d'agflow-rag) **ou** instance dédiée — arbitrage dans `01_ARCHITECTURE.md`. Mon penchant : schéma dédié, sauf besoin de découpler les cycles de backup.

## Commandes essentielles

```bash
# Backend
cd backend && uv sync
cd backend && uv run uvicorn docflow.app:app --reload        # :8080
cd backend && uv run pytest -v
cd backend && uv run ruff check src/ tests/
cd backend && uv run ruff format src/ tests/
cd backend && uv run mypy src/

# Migrations / apply idempotent (applique les .sql manquants dans l'ordre)
cd backend && uv run python -m docflow.db.apply

# Stack locale (app + postgres)
docker compose -f deploy/docker-compose.yml up -d
```

## Layout du code

```
docflow/
├── backend/
│   ├── pyproject.toml
│   ├── migrations/
│   │   └── 0001_init.sql         # schéma initial (fourni), immuable une fois appliqué
│   ├── src/docflow/
│   │   ├── app.py                # FastAPI app + lifespan (pool asyncpg, apply au boot)
│   │   ├── config/               # pydantic-settings, chargement env
│   │   ├── db/                   # pool asyncpg, apply (runner migrations), helpers requêtes
│   │   ├── secrets/              # résolveur ${vault://...} Harpocrate + fallback inline
│   │   ├── auth/                 # bootstrap admin, login local argon2 → JWT, RBAC, anti-lock-out
│   │   ├── oidc/                 # config OIDC, provisioning à la volée (milestone ultérieur)
│   │   ├── workspaces/           # CRUD workspace
│   │   ├── types/                # functional_type CRUD + hiérarchie
│   │   ├── properties/           # defs, constraints, allowed_values, values, validation
│   │   ├── documents/            # document arborescent + contenu markdown
│   │   ├── blocks/               # data_block + contrainte de type miroir
│   │   ├── mcp/                  # serveur MCP (milestone ultérieur)
│   │   └── schemas/              # DTOs API pydantic
│   └── tests/
├── frontend/                     # Vite + React + TS (écran admin types & statuts en premier)
├── deploy/
│   ├── Dockerfile                # AUCUN secret dans l'image
│   └── docker-compose.yml        # app + postgres (ou schéma dédié dans l'instance existante)
├── scripts/
│   ├── backup.sh                 # pg_dump chiffré (age/gpg)
│   └── restore.sh
├── specs/                        # ce corpus (00 → milestones)
└── CLAUDE.md
```

## Conventions de code

### Python (backend)

- Python 3.12+, **async/await partout** — jamais d'I/O bloquant dans un handler.
- pydantic v2, `extra="forbid"` sur tous les modèles de config et DTO d'entrée.
- Logs structurés via `structlog.get_logger(__name__)` — **jamais** `print()`. Redaction des secrets : un secret ne se déballe que par `.reveal()` au point d'injection, jamais dans un log.
- `type` hints partout, `from __future__ import annotations` en tête de fichier.
- **Fichiers max 300 lignes** ; classes SRP ; méthodes 5–15 lignes.
- Entrées utilisateur (slug, login, titre) : **validation regex stricte** avant tout usage.

### Base de données (remplace la section « état fichiers » de devpod-ui)

- Une migration = **un fichier SQL numéroté immuable** (`0001_`, `0002_`…). On **n'édite jamais** une migration déjà appliquée ; on en ajoute une.
- **Réconciliation additive** : ajout de colonne nullable = migration triviale ; renommage/suppression = migration explicite, revue, jamais automatique.
- asyncpg : **requêtes paramétrées uniquement** (`$1..$n`). Une f-string/`.format()` dans du SQL est une faute.
- Une opération de lifecycle = **une transaction** ; jamais d'état partiel.
- **Invariants non exprimables en DDL** (cohérence `functional_type` ↔ `document`, « exactly-one-of » `value`/`allowed_value_ref` au-delà du CHECK, enfant = même workspace que le parent) : validés **applicativement**, et **testés** (pas en revue manuelle).

### Sécurité (non négociable)

- Aucun secret en build arg, `ENV` de Dockerfile, layer, log, repo, **ni colonne en clair**. `client_secret` OIDC = `${vault://...}`.
- **Garde-fou anti-lock-out** : le dernier admin local connectable par mot de passe ne peut être ni désactivé ni supprimé. C'est un **test**, pas une intention.
- `fail closed` : aucun endpoint métier sans auth ; aucune ressource d'un workspace accessible sans en avoir le droit.

### Tests

- pytest + pytest-asyncio ; fixture `client` (TestClient httpx) ; base de test éphémère (transaction rollback ou base jetable).
- **TDD** : test rouge → impl → test vert → commit.
- Chaque milestone liste ses tests obligatoires ; les cas de rejet sécurité (anti-lock-out, slug dupliqué, isolation workspace, secret non déballé en log) sont des **tests**.
- Frontend (plus tard) : Vitest + React Testing Library ; `describe`/`it`.

## Règles de workflow

### Cycle de l'architecte

**Cadrer → Comprendre → Planifier → Agir.** L'utilisateur est architecte. Une question n'est pas une commande d'exécution. Une discussion n'est pas un feu vert. Ne JAMAIS sauter d'étape.

### Milestones

Exécution **dans l'ordre** M1 → M9. Ne pas démarrer M(n+1) sans la Definition of Done de M(n) validée. Chaque DoD inclut : lint + mypy + tests verts, pièges du milestone cochés, aucun secret en clair, migrations rejouables sur base vierge **et** sur base existante, README de test manuel.

### Branche de développement

**Tout le code se fait sur la branche `dev`.** Jamais `feat/*`, jamais sur `main` directement. Avant toute édition, vérifier `git branch --show-current` ; si autre branche, `git checkout dev`. Si `dev` n'existe pas, la créer depuis `main` à jour. Ne propose **jamais** `git checkout -b feat/...` — la consigne utilisateur prime sur tout workflow.

### Livraison

- Ne livre **jamais** le code, ni en test ni sur git, sans demande explicite.
- Ne modifie pas `.env` sauf si demandé.
- Commit messages en **français**, format conventionnel (`feat:`, `fix:`, `chore:`, `docs:`, `test:`…).

### Vérification avant validation

Avant de déclarer une tâche terminée, **toutes** ces étapes sont obligatoires :

1. Le code s'exécute sans erreur (ruff + mypy + build).
2. Le cas nominal fonctionne (test unitaire ou manuel).
3. Les imports ajoutés existent réellement.
4. Pas de régression sur les fichiers modifiés.
5. Si une migration est ajoutée : elle s'applique **sur base vierge ET sur base existante** sans erreur, et `apply` est idempotent (rejouable sans effet).
6. Aucun secret ni clé dans le diff (`git diff` relu sous cet angle).

### Discipline d'exécution

- Exécute directement, ne décris pas ce que tu vas faire — fais-le.
- N'explique pas les étapes intermédiaires. Rapporte le résultat final.
- Termine TOUTES les étapes d'un plan avant de faire un résumé.
- Si tu rencontres un problème, signale-le et propose une solution — ne l'ignore pas silencieusement.
- Si une API du corpus n'existe pas dans la version réelle : signale l'écart et propose l'équivalent vérifié — ne devine pas.

## Outils Claude Code

### Context7 — documentation live

**Quand** : avant d'écrire du code qui utilise FastAPI, pydantic v2, asyncpg, authlib, httpx, structlog, TanStack Query, Vite, i18next, le SDK MCP, etc. Les API évoluent, ne te fie pas à ta mémoire.

### Serena — navigation sémantique

**Quand** : avant un refactor, pour comprendre les dépendances entre modules, ou trouver tous les usages d'une fonction/classe.

### Superpowers skills

- `writing-plans` : rédiger un plan TDD avant de coder un milestone.
- `executing-plans` / `subagent-driven-development` : exécuter un plan tâche par tâche.
- `systematic-debugging` : debug d'un bug ou test qui échoue.
- `test-driven-development` : discipline TDD rigoureuse.
- `brainstorming` : explorer le design avant d'écrire.
- `verification-before-completion` : vérifier que le travail est réellement fini.

### /review

**Quand** : avant de présenter un changement multi-fichiers (>3 fichiers ou >100 lignes).

### /commit

**Quand** : quand l'utilisateur demande explicitement de committer. Format français conventionnel.

## Auto-amélioration

Quand tu fais une erreur ou que l'utilisateur te corrige :

- Ajoute une leçon dans `LESSONS.md`.
- Format : `- [module] description courte de l'erreur et de la bonne pratique`.
- Relis `LESSONS.md` en début de tâche qui touche un module mentionné.
- Ne dépasse pas 50 lignes — consolide les leçons similaires.

## Notifications de skills

Quand tu invoques une skill, affiche un marqueur **avant** d'exécuter :
> **`🟢 SKILL`** → *nom-de-la-skill* — raison en une phrase
