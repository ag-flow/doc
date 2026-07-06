# FE-14 — TypesAdmin : fragments sans `key`

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : frontend / TypesAdmin
- **Fichiers** : `frontend/src/pages/TypesAdmin.tsx:183-217`

## Description

`types.map((type) => (<> <tr key=…>…` — la `key` doit être sur le **fragment** (enfant direct du map), pas sur les `<tr>` internes. React réconcilie par index : après suppression d'un type, le DOM des lignes peut se réassocier incorrectement + warning console permanent.

## Impact

Réconciliation DOM fragile après suppression, warning console.

## Piste de correction

`<Fragment key={type.slug}>` au lieu du fragment court.
