# M5 — Propriétés values sur documents

## Objectif

- CRUD `properties_constraints` (min/max/min_length/max_length/pattern) sur les `properties_defs`.
- CRUD `properties_values` sur les documents : saisir / lire / supprimer les valeurs.
- Validation applicative complète (type, required, constraints, pattern regex).

## Routes exposées

### Contraintes (sous properties)

| Méthode | URL | Auth |
|---------|-----|------|
| GET | `/workspaces/{ws}/types/{type}/properties/{prop}/constraints` | admin |
| POST | `/workspaces/{ws}/types/{type}/properties/{prop}/constraints` | admin |
| DELETE | `/workspaces/{ws}/types/{type}/properties/{prop}/constraints/{kind}` | admin |

### Valeurs de document

| Méthode | URL | Auth |
|---------|-----|------|
| GET | `/workspaces/{ws}/documents/{doc_id}/values` | admin |
| PUT | `/workspaces/{ws}/documents/{doc_id}/values/{prop_slug}` | admin |
| DELETE | `/workspaces/{ws}/documents/{doc_id}/values/{prop_slug}` | admin |

## Invariants applicatifs

- **I-2** : `property_def_ref` de la valeur doit appartenir au `functional_type` du document.
- **I-3** : `text`/`int` → `value` renseigné, `allowed_value_ref` null. `restricted_list` → inverse.
- **I-4** : propriété `required` sans valeur → rejet à l'écriture.
- **I-6** : `pattern` réservé au type `text`. Rejet sur `int`/`restricted_list`.
- Contrainte min/max : vérifiée sur int. min_length/max_length : vérifiée sur text.
- Regex pattern : évaluée par l'application, pas par PostgreSQL.

## Definition of Done

- ruff + mypy propres
- Tests : set text/int/restricted_list, required rejet, constraint min/max rejet, pattern text uniquement, I-2 rejet
