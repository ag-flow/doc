# FE-09 — BacklinksPanel : navigation avec le mauvais bloc/workspace

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
> Backend (`references/service.py`) : `get_backlinks` renvoie désormais le **slug** du data_block de la source (`JOIN data_block db ON db.id = src.data_block_ref`, `db.slug AS bloc`) au lieu de l'UUID `data_block_ref` ; `BacklinkOut.bloc` passe de `uuid.UUID | None` à `str | None`. Frontend (`BacklinksPanel.tsx`) : l'URL est construite avec `bl.bloc` (bloc de la source) et non plus `blocSlug` (bloc courant) ; le fallback vers la route inexistante `/ws/${ws}/documents/${id}` est supprimé.
> ℹ️ Workspace : non problématique. La requête backlinks filtre `r.workspace_technical_key = $2` (workspace courant) et les références sont stockées avec le workspace de la source ; les backlinks retournés sont donc toujours du même workspace que le document consulté. `ws` (courant) est correct pour toutes les sources renvoyées — aucune info workspace supplémentaire n'est requise pour cette vue. (Un backlink cross-workspace n'apparaît pas dans cette liste, par construction de la requête.)

- **Gravité** : 🟠 MAJEUR
- **Confiance** : moyenne
- **Zone** : frontend / navigation
- **Fichiers** : `frontend/src/components/BacklinksPanel.tsx:47-52` ; `LinkSearchPopup.tsx` (mode « Parcourir » multi-workspaces) ; `App.tsx` (routes)

## Description

Le lien de backlink est construit avec le `blocSlug` **du document courant**, alors que la source peut appartenir à un autre bloc (le champ `bl.bloc` existe mais n'est pas utilisé) voire un autre workspace (LinkSearchPopup permet de lier des documents de n'importe quel workspace). Résultat : URL incohérente — panneau enfants vide (filtré sur le mauvais `block-documents`), fil d'Ariane et bouton « Documents » pointant sur le mauvais bloc, suppression renvoyant vers la mauvaise liste. De plus, le fallback `/ws/${ws}/documents/${id}` ne correspond à **aucune route** (catch-all → redirection /workspaces).

## Scénario de reproduction

1. Un document X d'un bloc A est référencé par un document Y d'un bloc B.
2. Ouvrir le panneau backlinks de X et cliquer sur Y.
3. Navigation vers une URL construite avec le bloc de X → contenu incohérent.

## Impact

Navigation par backlinks cassée dès que la source est dans un autre bloc/workspace.

## Piste de correction

Renvoyer bloc slug + workspace dans `BacklinkOut` et construire l'URL avec ces valeurs.
