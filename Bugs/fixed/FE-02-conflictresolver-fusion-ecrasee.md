# FE-02 — ConflictResolver : la fusion est écrasée par la sauvegarde suivante

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
> Dans `resolveConflict` (`DocumentEditor.tsx`), après le save de la version fusionnée on publie la réponse serveur (`updated`) dans le cache via `queryClient.setQueryData` — pour que `initialContent` reflète le contenu fusionné — puis on incrémente `editorEpoch`, qui entre dans la `key` de `MarkdownEditor` (`key={docId:editorEpoch}`). L'éditeur est donc remonté et recharge le contenu fusionné à la place du brouillon pré-fusion. La sauvegarde suivante ne peut plus réécraser les blocs serveur acceptés. S'appuie sur le mécanisme de remontage introduit en FE-01.

- **Gravité** : 🔴 CRITIQUE
- **Confiance** : haute
- **Zone** : frontend / versioning
- **Fichiers** : `frontend/src/pages/DocumentEditor.tsx:171-197` ; `frontend/src/components/MarkdownEditor.tsx:59-73`

## Description

Après `resolveConflict`, le serveur contient la version fusionnée et `expectedVersion.current` est mis à jour, mais l'éditeur BlockNote affiche toujours le **brouillon pré-fusion** (jamais rechargé, cf. `loadedRef` — voir [FE-01](FE-01-editeur-contenu-autre-document.md)). La sauvegarde suivante envoie ce brouillon avec la **bonne** `expected_version` → elle passe **sans 409** et **écrase silencieusement les blocs serveur acceptés** pendant la fusion.

## Scénario de reproduction

1. Conflit 409 lors d'une sauvegarde.
2. L'utilisateur accepte des modifications serveur dans le merge view.
3. « Enregistrer sur vN ».
4. Il continue à taper dans l'éditeur.
5. Sauvegarde → les modifications serveur acceptées disparaissent.

## Impact

La résolution de conflit ne protège rien : les données qu'on vient d'accepter sont perdues à la sauvegarde suivante. Perte de données silencieuse.

## Piste de correction

Après résolution, réinjecter `merged` dans l'éditeur (`replaceBlocks`) ou forcer le remontage de `MarkdownEditor` (`key`).
