# DOC-06 — `create_document` n'indexe pas les références du contenu initial

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : domaine / références
- **Fichiers** : `backend/src/docflow/documents/service.py:230-266`

## Description

`refresh_references` est appelé dans `update_document` (l.358) mais **jamais dans `create_document`**, alors que celui-ci accepte un `content` initial (et peut en générer un via `content_template`). Idem `create_document_in_block` (contenu NULL, moins grave).

## Scénario de reproduction

1. `POST /documents {content: "[cible](docflow://doc/<uuid>)"}`.
2. Le lien n'apparaît **ni** dans les backlinks de la cible **ni** dans la détection de liens cassés, tant que le doc n'est pas re-sauvegardé.

## Impact

Backlinks et détection de liens cassés incomplets pour tout document créé avec du contenu (fréquent via template).

## Piste de correction

Appeler `refresh_references(conn, doc_id, wk, initial_content)` dans la transaction de création.
