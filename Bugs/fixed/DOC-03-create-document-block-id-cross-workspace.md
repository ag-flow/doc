# DOC-03 — `create_document` accepte un `block_id` d'un autre workspace

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
> Hypothèse : ce correctif ferme le trou d'isolation (bloc du même workspace + parent
> dans le même bloc). La validation complète des types autorisés par position reste,
> comme avant, déléguée à `create_document_in_block` (mentionnée « idéalement » dans la piste).

- **Gravité** : 🔴 CRITIQUE
- **Confiance** : haute (vérifié par relecture directe)
- **Zone** : domaine / documents — isolation workspace
- **Fichiers** : `backend/src/docflow/documents/service.py:208-252` ; `backend/src/docflow/schemas/document.py` (`DocumentCreate.block_id`)

## Description

`POST /workspaces/{ws}/documents` insère `data.block_id` directement dans `data_block_ref` **sans aucune vérification** : ni existence dans le workspace, ni cohérence de type avec la position dans l'arbre (règles que `create_document_in_block` applique pourtant soigneusement). La FK ne garantit que l'existence **globale** du bloc, pas son appartenance au workspace.

```python
row = await conn.fetchrow(
    "INSERT INTO document (..., data_block_ref, exposed) VALUES (..., $6, $7) ...",
    ..., data.block_id, parent_exposed,
)
```

## Scénario de reproduction

1. `POST /workspaces/A/documents {block_id: <bloc du workspace B>}`.
2. Document créé dans le workspace A mais rattaché au bloc de B.
3. `GET /workspaces/B/blocks/x/documents` (requête `WHERE data_block_ref = $1`, `block_ops.py:26`) renvoie ce document dans l'arbre de B.

## Impact

Violation d'isolation workspace + arbre incohérent (le parent peut être dans un autre bloc que `block_id`). L'endpoint contourne aussi entièrement la contrainte de types autorisés par position.

## Piste de correction

Résoudre le bloc par `(workspace_technical_key, id)` et refuser sinon ; vérifier `parent.data_block_ref == block_id` ; idéalement factoriser la validation avec `create_document_in_block`.
