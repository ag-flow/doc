# FE-05 — Propriété `bool` : le premier toggle n'est jamais persisté (closure périmée)

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
> `save` (`hooks/useFieldState.ts`) accepte désormais une valeur explicite optionnelle (`value?`, défaut `state.value`). Le `onChange` du checkbox bool (`PropertyField.tsx`) calcule `next` et appelle directement `save(..., next)` au lieu de `setTimeout(commit, 0)` — on ne dépend plus de `state.status`/`state.value` encore périmés dans le rendu courant. Le premier toggle est donc persisté avec la bonne valeur, sans décalage d'un cran.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : frontend / propriétés
- **Fichiers** : `frontend/src/components/PropertyField.tsx:87-90` ; `frontend/src/hooks/useFieldState.ts`

## Description

`onChange` fait `setValue(...)` puis `setTimeout(commit, 0)`. `commit` est capturé dans le rendu **courant**, où `state.status` vaut encore `'idle'` → `if (state.status === 'dirty')` est faux → **aucun PUT**. Au second toggle, `commit` (du rendu précédent, désormais `dirty`) sauvegarde la **valeur du toggle précédent** : la persistance est décalée d'un cran par rapport à l'UI, sans indicateur.

## Scénario de reproduction

1. Cocher une propriété booléenne.
2. Recharger la page → la case est **décochée**.

## Impact

Les propriétés booléennes ne se sauvegardent pas de façon fiable (décalage d'un cran).

## Piste de correction

Faire porter le commit sur la valeur passée explicitement (`save(value)`) au lieu de relire `state` via closure.
