# FE-09 — BacklinksPanel : navigation avec le mauvais bloc/workspace

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
