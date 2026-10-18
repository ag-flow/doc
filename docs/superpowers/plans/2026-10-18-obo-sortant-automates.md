# OBO sortant des automates — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à un automate docflow de propager l'identité OBO de l'utilisateur déclencheur (les 3 en-têtes signés `x-portal-actor(-timestamp/-signature)`) sur son appel HTTP sortant, derrière un toggle par automate.

**Architecture:** L'acteur (GUID `app_user.identity`) est capté à l'ingress de la mutation, porté par le contexte de corrélation ambiant, persisté sur `document_event`, relu par le worker, puis signé et posé en en-têtes sortants — en réutilisant le contrat OBO figé (HMAC-SHA256 de `f"{actor}\n{timestamp}"`, secret = la clé API Bearer **du même appel**). Le RAG consomme déjà ces en-têtes sur `/api/v1/index` (`require_apikey_owner` → owner effectif par humain) : aucun changement côté RAG.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, pydantic v2, structlog, pytest ; migrations SQL immuables numérotées ; front Vite/React/TS + Vitest.

**Spec:** Mémoire `obo-sortant-automates.md` + contrat OBO v6 figé (globals `d0e2dad3`) ; code RAG de référence `admin-rag:backend/src/rag/auth/{obo,obo_resolver,workspace_auth}.py`, `api/workspace.py:110`.

## Global Constraints

- Tout le code sur la branche `dev` ; commits conventionnels en français.
- **Aucun couplage** avec le dépôt `rag` : on lit son contrat, on n'importe rien.
- Contrat OBO **byte-for-byte** : charge canonique = octets de `f"{actor}\n{timestamp}"`, HMAC-SHA256 hex, `timestamp` = unix secondes entières, fenêtre anti-rejeu 300 s (vérifiée côté RAG). Acteur = **GUID** (`app_user.identity`), jamais login/email/sub.
- Secret de signature = la clé API présentée sur le MÊME appel : valeur du header `Authorization` de l'automate **sans** le préfixe `Bearer ` (décision architecte 2026-10-18).
- Secrets : jamais en clair, jamais en log, jamais en argv. La signature et le secret ne sont jamais journalisés.
- Migration idempotente (vierge ET existante), `apply` rejouable.

## Prérequis d'instance (hors code — à vérifier avant d'activer, pas avant de coder)

- **P1 — Sync du GUID docflow↔RAG.** Le GUID envoyé doit être celui que RAG mappe via `email_for_identity`. Sans lui : `unknown_identity` côté RAG → repli clé → isolation perdue. Vérifier que `app_user.identity` (docflow) = le GUID du profil RAG du même humain.
- **P2 — Propriété des workspaces ragflow.** L'OBO n'isole que si chaque workspace ragflow est **possédé par l'humain** (pas partagé `owner_id IS NULL`, pas un compte de service). Vérifier `workspaces.owner_id` côté RAG.
- **P3 — État actuel du mélange.** Sortir la config vivante des automates (`automation.url`/`body_template`, `automation_workspace`) sur `test-doc-900` pour constater si le mélange existe aujourd'hui.

## Review Focus

- **force_obo activé mais event sans acteur** (mutation non authentifiée OBO, ou `identity` NULL) : l'appel ne doit PAS partir sous l'identité de la clé (ce serait le bug de mélange) → **defer** (re-mise en file), jamais dead-letter, jamais d'appel. Testé en Task 4.
- **Header `Authorization` absent ou non `Bearer`** alors que force_obo est activé : refus à la **configuration** (422), pas une 500 au dispatch. Testé en Task 4.
- **Acteur présent mais fenêtre anti-rejeu** : le `timestamp` est posé à l'instant du dispatch (pas de l'event), pour rester dans la fenêtre de 300 s même sur un event rejoué tardivement. Testé en Task 3.
- **Casse des en-têtes** : lecture/pose insensibles à la casse (le RAG lit en minuscules). Testé en Task 3.
- **Toggle OFF** : aucun en-tête OBO posé, comportement d'aujourd'hui strictement inchangé. Testé en Task 4.

---

### Task 1 : Persister l'acteur sur `document_event`

**Files:**
- Create: `backend/migrations/0081_document_event_actor.sql`
- Modify: `backend/src/docflow/events/outbox.py` (`_record_document_event`, ~l.172-185)
- Modify: `backend/src/docflow/observability/correlation.py` (`from_event_row`, l.205-219)
- Test: `backend/tests/events/test_outbox_actor.py`, `backend/tests/observability/test_correlation_actor.py`

**Interfaces:**
- Consumes: `corr.CorrelationContext.actor_guid` (déjà présent, l.54).
- Produces: colonne `document_event.actor_guid text` (nullable) ; `from_event_row(row)` renvoie désormais `actor_guid` peuplé.

- [ ] **Step 1 — Test rouge persistance.** Dans `test_outbox_actor.py` : lier un contexte `new_document_context(doc_key, actor_guid="11111111-1111-1111-1111-111111111111")`, appeler `enqueue(conn, event_code="document.created.v1", workspace_wk=wk, business={"documentId": str(doc_key)})`, puis `SELECT actor_guid FROM document_event WHERE document_ref=$1` → assert == le GUID.
- [ ] **Step 2 — Vérifier l'échec.** Run: `DATABASE_URL=... uv run pytest tests/events/test_outbox_actor.py -v` → FAIL (colonne inexistante).
- [ ] **Step 3 — Migration.** `0081_document_event_actor.sql` : `ALTER TABLE document_event ADD COLUMN IF NOT EXISTS actor_guid text;` + commentaire (relais OBO, nullable car une mutation non authentifiée OBO n'a pas d'acteur).
- [ ] **Step 4 — Écrire la colonne.** Dans `_record_document_event`, ajouter `actor_guid` à la liste de colonnes et `correlation.actor_guid` à la liste de valeurs ($9).
- [ ] **Step 5 — Appliquer + passer.** Run: `uv run python -m docflow.db.apply` puis le pytest de Step 1 → PASS. Rejouer `apply` → idempotent.
- [ ] **Step 6 — Test relecture.** Dans `test_correlation_actor.py` : `from_event_row({"correlation_id": "c", "actor_guid": "g"})` → `ctx.actor_guid == "g"` ; absent → `None`.
- [ ] **Step 7 — Implémenter la relecture.** `from_event_row` : ajouter `actor_guid=_opt(row.get("actor_guid"))` au `CorrelationContext` construit.
- [ ] **Step 8 — Passer.** Run le pytest observability → PASS.
- [ ] **Step 9 — Commit.** `feat(automates): document_event porte le GUID de l'acteur pour le relais OBO`

---

### Task 2 : Capter l'acteur à l'ingress MCP OBO

**Files:**
- Modify: `backend/src/docflow/observability/correlation.py` (nouvelle fonction `bind_actor`)
- Modify: `backend/src/docflow/mcp/router.py` (~l.127, autour de l'exécution de l'outil)
- Test: `backend/tests/observability/test_correlation_actor.py`, `backend/tests/mcp/test_mcp_obo_actor.py`

**Interfaces:**
- Produces: `corr.bind_actor(actor_guid: str) -> Token[CorrelationContext | None]` — lit `current()` ; s'il existe, le remplace par une copie avec `actor_guid` ; sinon crée `new_context("document", actor_guid=...)` ; bind et renvoie le token. `corr.reset(token)` restaure.
- Consumes: `resolve_actor_user` (mcp/obo.py) — déjà vérifie la signature ; le GUID acteur **est** la valeur de l'en-tête `x-portal-actor` ainsi validée.

- [ ] **Step 1 — Test rouge helper.** `bind_actor("g")` sans contexte courant → `current().actor_guid == "g"` ; avec un contexte existant (sans acteur) → le `correlation_id` est conservé, `actor_guid == "g"`. `reset(token)` → `current()` revient à l'état antérieur.
- [ ] **Step 2 — Vérifier l'échec.** Run: `uv run pytest tests/observability/test_correlation_actor.py::test_bind_actor -v` → FAIL.
- [ ] **Step 3 — Implémenter `bind_actor`** dans `correlation.py` (utiliser `dataclasses.replace` sur `current()`, sinon `new_context`).
- [ ] **Step 4 — Passer.** Run → PASS.
- [ ] **Step 5 — Test rouge ingress.** `test_mcp_obo_actor.py` : appel MCP d'une mutation de document avec en-têtes OBO valides (signés avec la clé API de la requête) → l'event écrit porte `actor_guid` = le GUID signé. Sans en-têtes OBO → `actor_guid` NULL.
- [ ] **Step 6 — Vérifier l'échec.** Run → FAIL (NULL au lieu du GUID).
- [ ] **Step 7 — Câbler l'ingress.** Dans `mcp/router.py`, quand `actor_user` est non-None, lire `request.headers.get("x-portal-actor")` (déjà vérifié), `token = corr.bind_actor(guid)` avant l'exécution de l'outil, `corr.reset(token)` en `finally`.
- [ ] **Step 8 — Passer.** Run → PASS.
- [ ] **Step 9 — Commit.** `feat(automates): l'ingress MCP OBO capte le GUID de l'acteur dans le contexte`

> Note scope : la capture **session web** (humain éditant via l'UI) est une tâche de suivi distincte — elle touche une dépendance d'auth partagée (`auth/deps.py:get_current_user`) et doit se faire via une dépendance FastAPI `yield` posée sur les routes de mutation de document, après inventaire de ces routes. À arbitrer : inclure maintenant ou livrer d'abord le chemin MCP.

---

### Task 3 : Toggle `force_obo` par automate — schéma, API, garde de config

**Files:**
- Create: `backend/migrations/0082_automation_force_obo.sql`
- Modify: `backend/src/docflow/schemas/automations.py` (DTO in/out + validation)
- Modify: `backend/src/docflow/automations/service.py` (lecture/écriture du champ)
- Test: `backend/tests/automations/test_force_obo_config.py`

**Interfaces:**
- Produces: colonne `automation.force_obo boolean NOT NULL DEFAULT false` ; champ `force_obo: bool` dans le DTO d'automate (in/out) ; `automations/service.py` renvoie `force_obo` dans la ligne lue par le worker.

- [ ] **Step 1 — Test rouge config.** Créer un automate `force_obo=True` **sans** header `Authorization: Bearer` → 422 (`obo_requires_bearer`). Avec le header → 201 et relecture `force_obo is True`.
- [ ] **Step 2 — Vérifier l'échec.** Run: `uv run pytest tests/automations/test_force_obo_config.py -v` → FAIL.
- [ ] **Step 3 — Migration + DTO + validation.** `0082` : `ADD COLUMN IF NOT EXISTS force_obo boolean NOT NULL DEFAULT false`. DTO : champ `force_obo`. Validation (service ou schéma) : `force_obo=True` exige un header actif `Authorization` commençant par `Bearer `.
- [ ] **Step 4 — Passer.** `apply` (+ rejeu idempotent) puis Run → PASS.
- [ ] **Step 5 — Style/types.** Run: `uv run ruff check src/ tests/` + `uv run mypy src/` → clean.
- [ ] **Step 6 — Commit.** `feat(automates): toggle force_obo par automate (schéma, API, garde config)`

---

### Task 4 : Signeur OBO sortant + pose au dispatch + garde fail-closed

**Files:**
- Create: `backend/src/docflow/automations/obo_sign.py`
- Modify: `backend/src/docflow/automations/worker.py` (`_prepare`/`_dispatch`, ~l.286-378)
- Test: `backend/tests/automations/test_obo_sign.py`, `backend/tests/automations/test_worker_obo.py`

**Interfaces:**
- Consumes: `automation["force_obo"]` (Task 3) ; `corr.from_event_row(event).actor_guid` (Task 1) ; `headers` déjà résolus dans `_dispatch` (worker.py:301-320) ; machinerie precheck `defer` (migration 0080).
- Produces:
  - `sign_actor(actor: str, timestamp: int, secret: str) -> str` — HMAC-SHA256 hex de `f"{actor}\n{timestamp}".encode()`, secret `secret.encode()` (miroir exact de `rag.auth.obo.sign_actor`).
  - `obo_headers(actor: str, secret: str, *, now: float | None = None) -> dict[str, str]` — `{"x-portal-actor": actor, "x-portal-actor-timestamp": str(int(now or time.time())), "x-portal-actor-signature": sign_actor(...)}`.
  - `bearer_secret(headers: dict[str, str]) -> str | None` — valeur du header `Authorization` (insensible casse) privée du préfixe `Bearer ` ; `None` si absent/non-Bearer.

- [ ] **Step 1 — Test rouge signeur.** `sign_actor("g", 1700000000, "k")` == valeur de référence `hmac` ; `obo_headers("g","k", now=1700000000)` : 3 clés en minuscules, signature cohérente ; `bearer_secret({"Authorization":"Bearer abc"}) == "abc"`, `{"authorization":"Bearer abc"} == "abc"`, `{} is None`.
- [ ] **Step 2 — Vérifier l'échec.** Run: `uv run pytest tests/automations/test_obo_sign.py -v` → FAIL.
- [ ] **Step 3 — Implémenter `obo_sign.py`** (ne jamais logger `secret`/signature).
- [ ] **Step 4 — Passer.** Run → PASS.
- [ ] **Step 5 — Test rouge dispatch.** `test_worker_obo.py` : (a) `force_obo=True`, event `actor_guid="g"`, header `Authorization: Bearer k` → la requête httpx sortante (mockée) porte les 3 en-têtes, et une vérif HMAC locale (sans importer `rag`) avec `"k"` **passe** ; `timestamp` dans la fenêtre de 300 s de `time.time()`. (b) `force_obo=True`, event **sans** `actor_guid` → **aucun** appel httpx, outcome `defer` (re-mise en file, pas de dead-letter), log `obo.actor_missing`. (c) `force_obo=False` → appel émis **sans** en-têtes OBO (régression nulle).
- [ ] **Step 6 — Vérifier l'échec.** Run: `uv run pytest tests/automations/test_worker_obo.py -v` → FAIL.
- [ ] **Step 7 — Câbler `_dispatch`.** Après construction de `headers` : si `automation["force_obo"]` → si `ctx.actor_guid` et `bearer_secret(headers)` présents : `headers.update(obo_headers(ctx.actor_guid, secret))` ; sinon → chemin `defer` (pas d'appel, log `obo.actor_missing` avec l'id automate, jamais le secret). Si `force_obo` faux → inchangé.
- [ ] **Step 8 — Passer + types.** Run → PASS ; `uv run ruff check src/ tests/` + `uv run mypy src/` → clean.
- [ ] **Step 9 — Commit.** `feat(automates): signe et pose les en-têtes OBO sortants, defer si acteur absent`

---

### Task 5 : Case « Forcer l'identité OBO » dans l'écran d'édition d'automate

**Files:**
- Modify: `frontend/src/components/AutomationDialog.tsx`
- Test: `frontend/src/test/AutomationDialog.test.tsx`

**Interfaces:**
- Consumes: champ `force_obo: boolean` du DTO d'automate (Task 3).

- [ ] **Step 1 — Test rouge.** Le dialog rend une case « Forcer l'identité OBO (OBO) » ; cochée → le payload de sauvegarde porte `force_obo: true` ; la case est désactivée avec un indice tant qu'aucun header `Authorization: Bearer` n'est présent (miroir UI de la garde de config, Task 3).
- [ ] **Step 2 — Vérifier l'échec.** Run: `npm run test -- AutomationDialog` → FAIL.
- [ ] **Step 3 — Implémenter** la case liée à l'état du formulaire + la désactivation conditionnelle.
- [ ] **Step 4 — Passer + build.** Run: `npm run test -- AutomationDialog` → PASS ; `npx tsc -b` ; `npm run build`.
- [ ] **Step 5 — Commit.** `feat(automates): case Forcer l'identité OBO dans l'écran d'édition`
