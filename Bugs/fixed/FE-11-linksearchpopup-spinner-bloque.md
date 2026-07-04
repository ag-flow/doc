# FE-11 — LinkSearchPopup : spinner bloqué et réponses hors-ordre

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : frontend / recherche de liens
- **Fichiers** : `frontend/src/components/LinkSearchPopup.tsx:180-191`

## Description

(a) Si la requête est vidée après un `setLoading(true)`, l'effet fait `return` **sans réinitialiser `loading`** → « … » permanent et le message « Aucun document trouvé » supprimé. (b) Le debounce annule le timer mais **pas les fetchs en vol** : une réponse lente d'une saisie précédente peut écraser les résultats de la saisie courante.

## Scénario de reproduction

Taper puis tout effacer rapidement → spinner « … » bloqué. Taper vite plusieurs requêtes → résultats d'une ancienne saisie affichés.

## Impact

Spinner bloqué et résultats de recherche incohérents.

## Piste de correction

`setLoading(false)` dans la branche vide + flag `cancelled` dans le cleanup de l'effet.
