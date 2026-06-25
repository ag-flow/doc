# M3 — Types fonctionnels & statuts

**Objectif.** CRUD `functional_type` (scope workspace, hiérarchie), `properties_defs` (définitions
de propriétés typées) et `properties_allowed_values` (valeurs autorisées — statuts pour les
`restricted_list`). C'est la surface API de l'écran admin prioritaire (M7).

**Dépend de.** M1, M2. Note : `functional_type` FK-ise sur `workspace`. Pour M3, le workspace
est créé en fixture de test ; le CRUD workspace est livré en M4.

---

## Périmètre

### 1 — Types fonctionnels (`functional_type`)

| Méthode | Route | Description |
|---|---|---|
| GET | `/workspaces/{ws}/types` | Liste les types (avec parent_slug résolu) |
| POST | `/workspaces/{ws}/types` | Crée un type |
| GET | `/workspaces/{ws}/types/{slug}` | Détail d'un type |
| PATCH | `/workspaces/{ws}/types/{slug}` | Modifie label et/ou parent |
| DELETE | `/workspaces/{ws}/types/{slug}` | Supprime (RESTRICT si enfants ou documents) |

Règles :
- `slug` unique par workspace (vérification DB unique constraint).
- `parent` optionnel. Si fourni : doit exister dans le même workspace.
- Cycle interdit (`A → B → A`) : vérification applicative sur la chaîne d'ancêtres.
- Suppression avec enfants → FK RESTRICT → 409 propre.

### 2 — Définitions de propriétés (`properties_defs`)

| Méthode | Route | Description |
|---|---|---|
| GET | `/workspaces/{ws}/types/{t}/properties` | Liste les propriétés du type |
| POST | `/workspaces/{ws}/types/{t}/properties` | Crée une propriété |
| GET | `/workspaces/{ws}/types/{t}/properties/{p}` | Détail |
| PATCH | `/workspaces/{ws}/types/{t}/properties/{p}` | Modifie label, default, required |
| DELETE | `/workspaces/{ws}/types/{t}/properties/{p}` | Supprime (RESTRICT si valeurs) |

Type de propriété : `text` | `int` | `restricted_list` (vérification CHECK en DB).

### 3 — Valeurs autorisées (`properties_allowed_values`)

Uniquement pour les propriétés de type `restricted_list`.

| Méthode | Route | Description |
|---|---|---|
| GET | `/workspaces/{ws}/types/{t}/properties/{p}/values` | Liste les valeurs |
| POST | `/workspaces/{ws}/types/{t}/properties/{p}/values` | Crée une valeur |
| GET | `/workspaces/{ws}/types/{t}/properties/{p}/values/{v}` | Détail |
| PATCH | `/workspaces/{ws}/types/{t}/properties/{p}/values/{v}` | Modifie label, position, color |
| DELETE | `/workspaces/{ws}/types/{t}/properties/{p}/values/{v}` | Supprime |

Règles :
- On ne peut créer des allowed_values que sur une propriété de type `restricted_list`.
- `slug` unique par propriété.

---

## Validation entrées

Tous les slugs : `^[a-z][a-z0-9_-]{0,98}[a-z0-9]$|^[a-z]$` — simplifié : `^[a-z][a-z0-9_-]*$`,
longueur 1–100. Validé par `@field_validator` pydantic avant tout accès DB.

---

## Modules

```
backend/src/docflow/
├── db/helpers.py            # _require_workspace, _require_type, _require_prop_def
├── schemas/types.py         # FunctionalTypeCreate / Update / Out
├── schemas/properties.py    # PropertiesDefCreate / Update / Out, AllowedValueCreate / Update / Out
├── types/__init__.py
├── types/service.py         # CRUD functional_type
├── types/router.py
├── properties/__init__.py
├── properties/service.py    # CRUD properties_defs + properties_allowed_values
└── properties/router.py
```

---

## Definition of Done

1. `uv run ruff check` + `uv run mypy src/` verts.
2. `uv run pytest -v` vert, incluant :
   - `test_create_type` → 201 + slug retourné.
   - `test_type_slug_unique_per_workspace` → 409.
   - `test_parent_must_be_same_workspace` → 422.
   - `test_cycle_detection` → 422.
   - `test_delete_type_with_children_rejected` → 409.
   - `test_create_property_def` → 201.
   - `test_allowed_value_only_on_restricted_list` → 422.
   - `test_create_allowed_value` → 201.
   - `test_unauthenticated_types_rejected` → 401.
3. Migrations : aucune migration ajoutée (tables déjà en 0001_init.sql).
4. Aucun secret, aucune f-string SQL avec valeur utilisateur.
