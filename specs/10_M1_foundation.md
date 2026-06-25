# M1 — Foundation

**Objectif.** Un squelette backend qui démarre, se connecte à Postgres, applique le schéma de façon idempotente, charge sa config et résout les secrets `${vault://...}`. Aucune logique métier encore — c'est le socle sur lequel M2→M9 s'appuient.

**Dépend de.** —

## Périmètre

1. **Squelette projet** : `pyproject.toml` (uv), `src/docflow/`, `tests/`, ruff + mypy configurés.
2. **Config** (`config/`) : modèles `pydantic-settings`, `extra="forbid"`, chargement depuis l'env. Champs : `database_url`, `admin_email`, `admin_password` (Secret), `jwt_secret` (Secret), `harpocrate_url` (optionnel), `log_level`.
3. **Couche DB** (`db/`) :
   - pool asyncpg ouvert/fermé dans le `lifespan` de FastAPI ;
   - **runner `apply`** (`python -m docflow.db.apply`) : crée `schema_migrations(version text primary key, applied_at timestamptz)`, liste les `migrations/*.sql` triés, applique ceux absents **dans une transaction par fichier**, enregistre la version. Idempotent.
   - helper `fetch`/`execute` paramétrés.
4. **Migration** : `migrations/0001_init.sql` (fourni) appliqué par le runner.
5. **Résolveur de secrets** (`secrets/`) : type `Secret` (ne s'imprime jamais, `.reveal()` au point d'usage), résolution `${vault://apiname:/path}` via Harpocrate (httpx), **fallback inline** si Harpocrate absent. Redaction structlog active.
6. **App** (`app.py`) : FastAPI + lifespan (pool + `apply` au boot), route `GET /health` (vérifie la connexion DB), structlog JSON.

## Tâches (TDD)

- [ ] `pyproject.toml` + arborescence + outils (`ruff`, `mypy`, `pytest`, `pytest-asyncio`).
- [ ] `config/settings.py` : `Settings(BaseSettings)`, test de chargement + rejet d'un champ inconnu (`extra="forbid"`).
- [ ] `db/pool.py` : ouverture/fermeture pool ; fixture de test sur base éphémère.
- [ ] `db/apply.py` : runner idempotent ; **test : double `apply` ne réapplique rien** ; test : applique `0001` sur base vierge.
- [ ] `secrets/secret.py` + `secrets/resolver.py` : `Secret` non déballé en repr/log ; résolution `${vault://}` (mock httpx) ; fallback inline ; **test : un log ne révèle jamais la valeur**.
- [ ] `app.py` : lifespan, `GET /health` 200 si DB OK ; test via TestClient.

## Definition of Done

1. `uv run ruff check` + `uv run mypy src/` verts.
2. `uv run pytest -v` vert (tous les tests ci-dessus).
3. `python -m docflow.db.apply` sur **base vierge** applique `0001`, puis **rejoué** ne fait rien.
4. `GET /health` renvoie 200 avec la DB up, 503 si DB down.
5. Aucun secret en clair dans un log (`Secret.__repr__` redacté) — vérifié par test.
6. Pièges `03` concernés cochés : migrations immuables, idempotence `apply`, requêtes paramétrées, secrets jamais en clair.
7. README de test manuel (`docs/M1.md`) : comment lancer, comment vérifier `/health` et l'idempotence.

## Notes d'implémentation

- `gen_random_uuid()` est natif PG13+. Si la cible est antérieure : `CREATE EXTENSION pgcrypto;` (à ajouter en tête de `0001` selon la version réelle — **vérifier la version installée**).
- Le seed du bootstrap admin n'est **pas** ici : c'est M2 (il dépend de la table `admin_user`, qui existe après `apply`, mais la logique de seed + login est un milestone à part).
- Consulter **Context7** avant d'écrire le code asyncpg / pydantic-settings / structlog : API à jour, pas de mémoire.
