# DOC-02 — Reparentage de document sans détection de cycle → boucle infinie Postgres

- **Gravité** : 🔴 CRITIQUE
- **Confiance** : haute (vérifié par relecture directe)
- **Zone** : domaine / documents
- **Fichiers** : `backend/src/docflow/documents/service.py:120-131` (`_validate_parent`), `362-366` (`update_document`)

## Description

`_validate_parent` ne vérifie que **l'existence** et **le workspace** du parent :

```python
async def _validate_parent(conn, wk, parent_id):
    parent_wk = await conn.fetchval("SELECT workspace_technical_key FROM document WHERE doc_technical_key = $1", parent_id)
    if parent_wk is None: raise 422
    if parent_wk != wk: raise 422
```

Contrairement aux types fonctionnels (`types/service.py::_check_no_cycle` existe), **aucun contrôle de cycle** pour les documents : `PATCH /documents/{id}` avec `parent_id = id` (auto-parent) ou `parent_id = <descendant>` passe.

## Scénario de reproduction

1. Doc A parent de B.
2. `PATCH B {parent_id: A}` → OK.
3. `PATCH A {parent_id: B}` → **accepté** (cycle A→B→A créé).
4. `GET /documents/A/exposed` exécute la CTE récursive `UNION ALL` (`service.py:429-445`) **sans garde de cycle → boucle infinie côté Postgres** : la requête ne termine jamais, la connexion du pool reste bloquée. Tout parcours d'arbre (front, export) boucle aussi.

## Impact

Déni de service : une connexion du pool est consommée indéfiniment, l'arborescence devient inparcourable. Reproductible par n'importe quel utilisateur autorisé sur le workspace.

## Piste de correction

Dans `update_document`, quand `parent_id` change : remonter la chaîne d'ancêtres du nouveau parent (comme `_check_no_cycle` des types) et refuser si `doc_id` y figure ou si `parent_id == doc_id`. Verrouiller la ligne pendant le check pour éviter les courses.
