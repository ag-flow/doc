# « Connecter à Harpocrate » — déclarer un endpoint vault sans copier-coller de clé — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Dans docflow, un utilisateur déclare un endpoint vault via un parcours « Se connecter avec Harpocrate » (type OAuth Authorization Code + PKCE, Harpocrate n'étant PAS un IdP) : au retour, docflow crée atomiquement un `user_secret` `HARPOCRATE_API_KEY` local chiffré + un `vault_wallet` qui le référence — sans que le token transite par le navigateur.

**Architecture:** Backend FastAPI : 2 routes (`connect/start` dépose la demande via `harpocrate.connect.start` et stocke le `ConnectState` chiffré dans une table à TTL ; `connect/callback` GET navigateur vérifie le `state`↔utilisateur, échange via `connect.finish`, crée secret+endpoint en une transaction). Front : bouton dans l'onglet Vault + lecture du résultat au retour. Aucune modification de Harpocrate.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, pydantic v2, `harpocrate>=0.8.0` (module `connect`, `joserfc`), Fernet (`encrypt_str`), structlog ; front Vite/React/TS + Vitest ; migrations SQL immuables.

**Spec:** Feature docflow `b95ed9f4-3356-41ec-a2bf-f771208bc7f4` (critères d'acceptation 1–10, obligations de sécurité, latitude). Contrat : harpocrate `3d5af640-...` (routes `/v1/connect/par`, `/v1/connect/token`, invariants, erreurs). Carte du socle : rapport d'exploration de session (interfaces exactes citées ci-dessous).

## Global Constraints

- Branche `dev` uniquement ; commits conventionnels français. Secrets jamais en clair/log/argv.
- **Obligations de sécurité (non négociables, de la spec)** : `code_verifier` + clé privée EC éphémère (`ConnectState`) restent **côté serveur**, jamais navigateur/cookie/URL/log ; clé privée jetée après échange ou à l'expiration (15 min). `state` **lié à la session** de l'utilisateur et vérifié **avant** tout échange. Jamais journaliser token / `dkey` / `jwe` / `code` / `code_verifier`. Token stocké par le mécanisme de secret existant (`encrypt_str`, Fernet), jamais en clair. `access_denied` / `state` inconnu ou périmé / échec d'échange ⇒ configuration **inchangée** + raison lisible, jamais le token.
- **Interdits (spec)** : modifier Harpocrate ; supprimer/masquer la saisie manuelle de clé ; faire passer scellé/`code_verifier`/token par le navigateur.
- **Décisions prises (latitude)** : `permissions=1` (read — docflow ne fait que `client.secrets.get`) ; `ttl_days=null` ; `client_id` configurable (défaut `docflow`) ; URL de retour = route backend GET `/api/admin/vault/connect/callback`.
- Migration idempotente (vierge ET existante), `apply` rejouable.

## Prérequis (vérifiés le 2026-10-23 — ne pas recommencer sauf échec)

- Flux Harpocrate en ligne : `GET {harpocrate}/v1/openapi-connect.json` → 200 (vault.yoops.org, harpocrate.yoops.org).
- SDK 0.8.0 téléchargeable (Task A le pose). Socle T2 (endpoint↔secret) présent dans le code.
- **Coordination hors code (bloque la validation LIVE, pas le build/tests)** : faire **déclarer docflow comme `connect-client`** par un admin Harpocrate (écran « Applications connectées ») — `client_id=docflow` + redirect URIs EXACTES par env :
  - prod : `https://doc.yoops.org/api/admin/vault/connect/callback`
  - test : `https://<host-test>/api/admin/vault/connect/callback` (à fixer selon la machine de test)
  Sans déclaration : `POST /v1/connect/par` renvoie `400 invalid_client` / `invalid_redirect_uri`. Les tests (critère 10) tournent avec un Harpocrate **simulé** ; la validation réelle attend cette déclaration.

## Review Focus

- **`state` étranger/périmé** (autre utilisateur, autre navigateur, >15 min) : le callback refuse SANS appeler Harpocrate, rien n'est créé (critère 4). Testé Task C.
- **Rejeu du `code`** (refresh, back) : usage unique via `consumed_at`, pas de 2e config, pas de 500, message clair (critère 5). Testé Task C.
- **Échec d'échange / `access_denied` / Harpocrate injoignable** : rien enregistré, aucune trace de token/`jwe`/`code` dans les logs (critère 6). Testé Task C + assertion anti-log.
- **Atomicité** : échec de l'INSERT endpoint après création du secret (ou l'inverse) ⇒ **aucun** des deux persistant (les deux ou aucun). Testé Task C.
- **Alias en doublon au retour** : la clé obtenue n'est pas perdue en silence — message « non enregistrée » (critère 7). Testé Task C.
- **Isolation propriétaire** : un retour arrivant dans la session d'un autre utilisateur est refusé (critère 9). Testé Task C.

---

### Task A : Monter le SDK harpocrate à 0.8.0 (module `connect`)

**Files:**
- Modify: `backend/pyproject.toml` (pin + source wheel), `backend/uv.lock` (via `uv lock`)
- Test: `backend/tests/test_harpocrate_connect_available.py`

**Interfaces:**
- Produces: `harpocrate.connect.{start, finish, ConnectState, ConnectResult}` + `harpocrate.exceptions.ConnectError(error_code)` importables ; `joserfc` présent.

- [ ] **Step 1 — Test rouge.** `test_harpocrate_connect_available.py` : `import harpocrate.connect as c; assert hasattr(c,'start') and hasattr(c,'finish'); from harpocrate.exceptions import ConnectError`.
- [ ] **Step 2 — Échec.** Run: `uv run pytest tests/test_harpocrate_connect_available.py -v` → FAIL (0.6.0 installé, pas de `connect`).
- [ ] **Step 3 — Relever le pin.** `pyproject.toml` : `harpocrate>=0.8.0` ; source `harpocrate = { url = "https://vault.yoops.org/v1/sdk/by-filename/harpocrate-0.8.0-py3-none-any.whl" }`. `uv lock && uv sync`. Vérifier que `joserfc` est tiré.
- [ ] **Step 4 — Non-régression SDK.** Confirmer que `docflow.secrets.vault_fetch` (`client.secrets.get`, `PermissionDenied`, `VaultHttpError`) fonctionne toujours en 0.8.0 : `uv run pytest tests/ -k "vault_fetch or resolver" -v`.
- [ ] **Step 5 — Passer + commit.** Run Step 1 → PASS. Commit : `chore(secrets): SDK harpocrate 0.8.0 (module connect)`.

---

### Task B : Table d'état éphémère `connect_flow` + repo

**Files:**
- Create: `backend/migrations/0083_connect_flow.sql` (max actuel = 0082 ; confirmer au moment du dev), `backend/src/docflow/vault/connect_store.py`
- Test: `backend/tests/test_connect_store.py`

**Interfaces:**
- Produces, dans `connect_store.py` :
  - `async def put(conn, *, state: str, owner_id: uuid.UUID, state_blob_enc: str, pending_enc: str, expires_at: datetime) -> None` — INSERT, clé = `sha256(state)`.
  - `async def take_active(conn, *, state: str, owner_id: uuid.UUID, now: datetime) -> Row | None` — SELECT par `sha256(state)` NON consommé ET non expiré ET `owner_ref == owner_id` ; retourne la ligne (blobs chiffrés) ou None. NE marque pas encore consommé.
  - `async def mark_consumed(conn, *, state: str) -> None`.
  - `async def delete_expired(conn, *, now: datetime) -> int`.
- Table `connect_flow` : `id uuid pk`, `state_hash text unique not null` (sha256 hex), `owner_ref uuid not null references app_user(id) on delete cascade`, `state_enc text not null` (ConnectState chiffré), `pending_enc text not null` (params endpoint {name,url,description} chiffrés), `created_at timestamptz not null default now()`, `expires_at timestamptz not null`, `consumed_at timestamptz`.

- [ ] **Step 1 — Test rouge.** `put` puis `take_active` (bon owner, non expiré) rend la ligne ; `take_active` avec un autre `owner_id` → None ; après `expires_at` → None ; après `mark_consumed` → None ; `delete_expired` supprime les périmés. Chiffrement opaque (le blob stocké ≠ clair).
- [ ] **Step 2 — Échec.** Run: `uv run pytest tests/test_connect_store.py -v` → FAIL.
- [ ] **Step 3 — Migration + repo.** Écrire `0083_connect_flow.sql` (idempotent, index sur `state_hash` et `expires_at`) + `connect_store.py`. Ne JAMAIS stocker `state` en clair (seulement son sha256), ni les blobs en clair.
- [ ] **Step 4 — Appliquer + passer.** `uv run python -m docflow.db.apply` (idempotent rejoué) puis Step 1 → PASS.
- [ ] **Step 5 — Purge.** Brancher `delete_expired` sur un worker/t’tick existant si trivial ; sinon documenter l'appel. (Latitude : ne pas bloquer sur un worker dédié — un nettoyage best-effort au `start` suffit si aucun worker n'est à portée.)
- [ ] **Step 6 — Style/types + commit.** `ruff`/`mypy` verts. Commit : `feat(vault): table connect_flow pour l'état éphémère du parcours Harpocrate`.

---

### Task C : Service + 2 routes backend du parcours

**Files:**
- Create: `backend/src/docflow/vault/connect.py` (service du parcours)
- Modify: `backend/src/docflow/vault/router.py` (2 routes), `backend/src/docflow/vault/user_secrets.py` + `endpoints.py` (extraire des helpers INSERT prenant `conn` pour l'atomicité), `backend/src/docflow/config/settings.py` (`harpocrate_connect_client_id: str = "docflow"`)
- Test: `backend/tests/test_vault_connect.py`

**Interfaces:**
- Consumes : `harpocrate.connect.start/finish` (Task A) ; `connect_store` (Task B) ; `encrypt_str`/`decrypt_str` (`crypto.py`) ; `require_authenticated` (`auth/deps.py`) ; `effective_base_url` (`app.py`).
- Produces :
  - Helpers conn-composables : `_insert_user_secret(conn, *, owner_id, slug, label, value_enc, secret_type) -> uuid.UUID` et `_insert_vault_wallet(conn, *, owner_id, name, url, description, api_key_secret_ref) -> VaultWalletOut`, extraits des fonctions existantes (qui les réutilisent ensuite, DRY).
  - `async def start_connect(pool, *, user, base_url, name, url, description, redirect_uri, client_id, enc_key, now) -> str` (renvoie l'URL navigateur). Appelle `connect.start(url, client_id, redirect_uri, permissions=1, ttl_days=None)` via `asyncio.to_thread`, chiffre `ConnectState.to_dict()` et les params endpoint, `connect_store.put`.
  - `async def finish_connect(pool, *, user, state, code, error, enc_key, now) -> ConnectOutcome` — vérifie `take_active(state, owner=user.id)` (sinon `invalid_state`) ; si `error==access_denied` → `denied` + `mark_consumed` ; sinon `connect.finish(pending, code, state)` via `to_thread`, puis **transaction unique** : `_insert_user_secret(HARPOCRATE_API_KEY, value_enc=encrypt_str(token)) ` + `_insert_vault_wallet(api_key_secret_ref=...)` + `mark_consumed` ; mappe `ConnectError.error_code` et `UniqueViolation(alias)` → outcomes `error`/`duplicate`. Jamais logger token/jwe/code.
  - `ConnectOutcome` = enum/str : `ok | denied | invalid_state | already | duplicate | error`.
- Routes (sous `/api`, auth `require_authenticated`) :
  - `POST /api/admin/vault/connect/start` body `{name, url, description}` → `{browser_url}` (201/200).
  - `GET /api/admin/vault/connect/callback?code&state&error` → **302** vers `/admin/vault?connect=<outcome>` (jamais de token dans l'URL/headers).

- [ ] **Step 1 — Tests rouges (Harpocrate simulé).** Monkeypatch `harpocrate.connect.start/finish`. Cas : (1) nominal → secret HARPOCRATE_API_KEY local chiffré + wallet le référençant créés, 302 `connect=ok` ; (2) `error=access_denied` → 302 `denied`, rien créé ; (3) `state` d'un autre owner / inconnu / expiré → 302 `invalid_state`, `finish` **non appelé** ; (4) rejeu (même state consommé) → 302 `already`, pas de 2e config ; (5) `finish` lève `ConnectError("invalid_grant")` → 302 `error`, rien créé ; (6) atomicité : forcer l'échec de l'INSERT wallet → le secret n'est pas persistant non plus ; (7) alias déjà pris → 302 `duplicate` ; (8) anti-log : le token simulé n'apparaît dans AUCUN record de log capturé.
- [ ] **Step 2 — Échec.** Run: `uv run pytest tests/test_vault_connect.py -v` → FAIL.
- [ ] **Step 3 — Implémenter.** Extraire les helpers INSERT (refactor DRY de `create_secret`/`create_wallet` pour partager l'INSERT sur une `conn`), écrire `connect.py` + les 2 routes + le setting. `redirect_uri` = `f"{effective_base_url(request)}/api/admin/vault/connect/callback"`. Permissions=1, ttl_days=None.
- [ ] **Step 4 — Passer + types.** Run → PASS ; `ruff`/`mypy` verts. Vérifier que les routes existantes de création manuelle (`POST /api/admin/vault/wallets`, `/api/admin/secrets`) sont inchangées (critère 8).
- [ ] **Step 5 — Commit.** `feat(vault): parcours « Connecter à Harpocrate » (start + callback, création atomique)`.

---

### Task D : Front — bouton « Connecter à Harpocrate » + résultat au retour

**Files:**
- Modify: `frontend/src/pages/VaultWalletsTab.tsx`, `frontend/src/lib/api.ts`, `frontend/src/pages/VaultAdmin.tsx` (lecture de `?connect=`), `frontend/src/locales/fr.json`
- Test: `frontend/src/test/VaultWalletsTab.test.tsx` (créer si absent), `frontend/src/test/VaultAdmin.test.tsx`

**Interfaces:**
- Consumes : `POST /api/admin/vault/connect/start` (Task C) ; redirection `/admin/vault?connect=<outcome>`.
- Produces : `vaultApi.connectStart({name, url, description}) -> {browser_url}` dans `api.ts`.

- [ ] **Step 1 — Test rouge.** Dans `VaultWalletsTab.test.tsx` : un bouton « Connecter à Harpocrate » est rendu, **désactivé** tant que `name` (alias) et `url` ne sont pas saisis ; au clic, `vaultApi.connectStart` est appelé avec `{name,url,description}` et la navigation pleine page part vers `browser_url` (mock `window.location`). La saisie manuelle (select secret + créer) reste présente et fonctionnelle (critère 8).
- [ ] **Step 2 — Résultat au retour.** Dans `VaultAdmin.test.tsx` : au montage avec `?connect=ok` → message succès + invalidation des listes `['harpocrate-keys']` et wallets ; `?connect=denied|invalid_state|already|duplicate|error` → message lisible correspondant ; aucun token affiché.
- [ ] **Step 3 — Échec.** Run: `npm run test -- VaultWalletsTab VaultAdmin` → FAIL.
- [ ] **Step 4 — Implémenter** le bouton + `connectStart` + la lecture de `?connect=` (toast + refetch + nettoyage du query param) + libellés fr (en dur cohérent avec l'écran, i18n `vault.*` si l'écran l'utilise déjà).
- [ ] **Step 5 — Passer + build + commit.** `npm run test -- VaultWalletsTab VaultAdmin` → PASS ; `npx tsc -b` ; `npm run build`. Commit : `feat(vault): bouton « Connecter à Harpocrate » et résultat au retour`.

---

### Task E : Documentation du contrat consommé + compte rendu permissions

**Files:**
- Modify/Create: article docflow bloc `documentation` du workspace `docflow` décrivant le parcours côté docflow (routes `connect/start`/`callback`, redirect URIs par env à déclarer, permission `read`/1 justifiée, stockage `connect_flow`).

- [ ] **Step 1 — Publier l'article** (via les outils MCP `doc`) dans `docflow › documentation` : intention, les 2 routes, les redirect URIs exactes à faire déclarer, la décision permission=1 (justifiée par `vault_fetch` lecture seule) et ttl=null, le TTL 15 min + usage unique. Référencer le contrat harpocrate `3d5af640`. (interface-contracts : une interface consommée + une route exposée se documentent.)
- [ ] **Step 2 — Vérifier** qu'aucune divergence n'est introduite avec la saisie manuelle existante ; lier l'article à l'épic.

> Note : pas de nouvelle spec OpenAPI à joindre (on *consomme* le contrat Harpocrate déjà spécifié ; les 2 routes docflow sont internes à l'UI, documentées en prose).
