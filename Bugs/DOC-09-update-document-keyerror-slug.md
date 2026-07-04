# DOC-09 — `update_document` : `KeyError` sur conflit de slug lors d'un déplacement

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : domaine / documents
- **Fichiers** : `backend/src/docflow/documents/service.py:384-388`

## Description

L'index `document_slug_sibling_uix (workspace, parent, slug)` peut être violé par un simple changement de `parent_id` (nouveau frère portant le même slug). Le handler `except UniqueViolationError` fait `raw['slug']` alors que `slug` n'est **pas** dans le payload (seul `parent_id` a changé) → `KeyError` → **500** au lieu du 409 explicatif.

## Scénario de reproduction

1. Doc `foo` sous parent P1 ; doc `foo` existe déjà sous parent P2.
2. `PATCH /documents/{id_du_premier} {parent_id: P2}` (sans `slug` dans le body).
3. Violation d'unicité → `raw['slug']` → `KeyError` → 500.

## Impact

500 opaque au lieu d'un 409 exploitable lors d'un déplacement conflictuel.

## Piste de correction

`raw.get('slug')` ou message dédié au cas déplacement.
