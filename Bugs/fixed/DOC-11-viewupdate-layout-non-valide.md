# DOC-11 — `ViewUpdate.layout` non validé → 500 au lieu de 422

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : domaine / vues
- **Fichiers** : `backend/src/docflow/views/service.py:44-53, 216-223`

## Description

`ViewCreate` valide `layout ∈ {table, board}`, `ViewUpdate` non. `PATCH {layout: "kanban"}` part en UPDATE et se fait rejeter par le CHECK SQL → `CheckViolationError` non attrapée → **500**.

## Scénario de reproduction

`PATCH /views/{slug} {layout: "kanban"}` → 500.

## Impact

500 opaque au lieu d'un 422 de validation.

## Piste de correction

Ajouter le même `field_validator` sur `ViewUpdate`.
