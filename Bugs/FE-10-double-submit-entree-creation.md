# FE-10 — Double-submit par Entrée dans les dialogues de création

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : frontend / création documents
- **Fichiers** : `frontend/src/components/AddDocumentDialog.tsx:87-103, 144` ; `DocumentChildrenPanel.tsx:40-58, 131` (+ `RemotePage.tsx:430`)

## Description

Le bouton est bien `disabled={submitting}`, mais le handler `onKeyDown Enter` appelle `handleSubmit`/`createChild` qui **ne vérifient pas `submitting`**. Deux appuis rapides sur Entrée → deux POST → deux documents créés (dans AddDocumentDialog, le second passe la garde slug car le cache n'est pas encore invalidé). Même absence de garde `isPending` sur « Enregistrer » de `PointForm` (`RemotePage.tsx`).

## Scénario de reproduction

Remplir le dialogue et appuyer deux fois rapidement sur Entrée → deux documents créés.

## Impact

Créations en double.

## Piste de correction

`if (submitting) return` en tête des handlers de soumission.
