# DOC-12 — `allowed_types` avec `parent_id` : fuite inter-workspace

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : domaine / blocks
- **Fichiers** : `backend/src/docflow/documents/block_ops.py:162-172`

## Description

`GET /blocks/{slug}/allowed-types?parent_id=X` accepte un `parent_id` de **n'importe quel** workspace/bloc et renvoie les types enfants du type de ce document (fuite de slugs/labels inter-workspace, résultat sans rapport avec le bloc interrogé). `create_document_in_block` revalide correctement, donc pas d'écriture corrompue par ce chemin.

## Scénario de reproduction

`GET /workspaces/A/blocks/x/allowed-types?parent_id=<doc du workspace B>` → renvoie les types enfants du type du doc de B.

## Impact

Fuite d'information (slugs/labels de types) entre workspaces.

## Piste de correction

Vérifier `workspace_technical_key = wk AND data_block_ref = block_id` sur le parent.
