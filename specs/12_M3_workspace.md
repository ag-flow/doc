# M3 — Workspace

**Objectif.** Gérer le cycle de vie du **workspace**, la partition racine à laquelle tout le contenu est rattaché (`workspace_technical_key` sur chaque ligne). Création, consultation, édition, archivage/suppression gardés. Exposé en trois faces : CLI (admin local), API HTTP (admin authentifié), puis IHM (sélection du workspace courant).

**Dépend de.** M1 pour la couche données/service/CLI (déjà livrée). La face HTTP dépend de **M2** (auth) ; la face IHM dépend de **M2 + le front**.

**Pourquoi ce milestone précède les types.** L'écran « types & statuts » et les documents sont scopés au workspace : sans workspace existant, ils n'ont pas de contexte. Le workspace est donc un **prérequis**, pas une fonctionnalité parmi d'autres.

## Règles métier

- **Slug = clé d'adressage immuable.** Unique globalement (`UNIQUE(slug)`), validé `^[a-z0-9][a-z0-9_-]*$`, max 64. Une fois créé, le slug **ne se renomme pas** (il sert d'URL et de référence) : seuls `label` et `description` sont éditables.
- **Suppression = destructive.** `ON DELETE CASCADE` détruit **tout** le contenu du workspace (types, documents, blocs, propriétés, valeurs). Interdiction d'une suppression « légère » : voir la décision ci-dessous.
- **RBAC.** `create` / `update` / `archive` / `delete` = **admin**. `list` / `get` = admin. Le modèle n'a pas d'appartenance par utilisateur → tous les workspaces sont visibles aux admins ; un cloisonnement multi-tenant par user (table de membership) est **hors périmètre** ici.

## Décision à acter — archivage vs suppression physique

Hard delete d'un workspace = perte **irréversible** de tout son contenu (cascade). Recommandation propre, dans la ligne « destructif = explicite » :

- **Archivage par défaut** via une colonne additive `archived_at timestamptz null` (migration `0002_workspace_archived.sql`, additive donc triviale). `list`/`get` filtrent `archived_at is null` par défaut (option `include_archived`).
- **Purge physique** = action séparée, exceptionnelle, gardée : admin only + **confirmation par re-saisie du slug**. Jamais le geste par défaut de l'IHM.

→ À valider. Si tu refuses l'archivage, on garde uniquement la purge gardée + confirmée (pas de colonne `archived_at`).

## Périmètre & phases

### Phase A — Données / service / CLI (dépend M1) — ✅ livré

- `workspaces/repository.py` (requêtes paramétrées), `workspaces/service.py` (validation slug + unicité), `workspaces/cli.py` (`create` / `list`), `schemas/workspace.py`, `tests/test_workspace.py`.
- **À compléter dans ce milestone** : `service.update_workspace` (label/description, refus de toute modif de slug), `service.archive_workspace` (si décision archivage), CLI `update` / `archive`.

### Phase B — API HTTP (dépend M2)

Router `workspaces/router.py`, gated `Depends(require_admin)` (fourni par M2) :

| Méthode & route | Effet | Codes |
| --- | --- | --- |
| `POST /workspaces` | crée | 201 `WorkspaceOut` ; 409 slug dupliqué ; 422 slug invalide |
| `GET /workspaces` | liste (option `include_archived`) | 200 |
| `GET /workspaces/{slug}` | détail | 200 / 404 |
| `PATCH /workspaces/{slug}` | maj `label`/`description` ; un `slug` dans le body est **refusé** | 200 / 404 / 422 |
| `POST /workspaces/{slug}/archive` | archive (si décision archivage) | 200 / 404 |
| `DELETE /workspaces/{slug}?confirm={slug}` | purge gardée ; `confirm` ≠ slug → refus | 204 / 400 / 404 |

**Scoping du contenu.** Les ressources filles s'adressent **sous** le workspace : `/workspaces/{slug}/functional-types`, `/workspaces/{slug}/documents`, etc. Scoping explicite et RESTful ; le `workspace_technical_key` est résolu depuis le slug de chemin, jamais passé par le client.

### Phase C — IHM (dépend M2 + front)

- Écran **liste des workspaces** + **création** (slug/label/description ; slug validé côté client par le même regex).
- **Sélection** d'un workspace → définit le **contexte courant** ; ce contexte scope les écrans suivants (types & statuts, documents).
- **Édition** label/description ; slug affiché en lecture seule (badge monospace).
- **Archivage/purge** gardé : confirmation par re-saisie du slug, jamais en un clic.

## Tâches (TDD)

Phase A (compléter) :
- [ ] `update_workspace(conn, slug, label?, description?)` ; **test : tentative de changer le slug → refusée**.
- [ ] (si archivage) `archive_workspace` + filtre `archived_at is null` dans `list`/`get` ; tests.
- [ ] CLI `update` / `archive`.

Phase B :
- [ ] `require_admin` injecté ; **401 sans auth, 403 non-admin** (testés).
- [ ] `POST` : 201 / 409 doublon / 422 slug invalide.
- [ ] `GET` liste & détail ; `PATCH` (refus du slug) ; archive/delete gardé (`confirm` mismatch → 400).

Phase C :
- [ ] Vitest : rendu liste, formulaire création (validation slug live), sélection → contexte courant, slug read-only, confirmation de purge.

## Definition of Done

1. ruff + mypy + tests verts (back) ; Vitest vert (front).
2. **Phase A** : créer / lister / mettre à jour / archiver un workspace en CLI contre un vrai Postgres ; **immuabilité du slug vérifiée**.
3. **Phase B** : les routes répondent comme spécifié ; `fail closed` (401/403) testé ; doublon → 409, slug invalide → 422.
4. **Phase C** : créer **et** sélectionner un workspace depuis l'IHM ; le contexte scope bien l'écran suivant.
5. **Destruction protégée** : impossible de détruire le contenu d'un workspace sans confirmation explicite (test de rejet).
6. Pitfalls cochés : slug immuable, suppression gardée, requêtes paramétrées, RBAC admin, aucun secret en clair.

## Notes

- Migration `0002_workspace_archived.sql` (si archivage) : `alter table workspace add column archived_at timestamptz;` — additive, instantanée, conforme à la réconciliation additive.
- **Context7** avant le code router (FastAPI dependencies, status codes) et le front (TanStack Query, react-router).
- Le `require_admin` de la phase B est une dépendance dure de M2 : ne pas démarrer la phase B avant la DoD de M2.
