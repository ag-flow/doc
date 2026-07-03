# FE-01 — Éditeur affiche/sauvegarde le contenu d'un autre document

- **Gravité** : 🔴 CRITIQUE
- **Confiance** : haute
- **Zone** : frontend / éditeur — intégrité du versioning
- **Fichiers** : `frontend/src/components/MarkdownEditor.tsx:59-73` ; `frontend/src/pages/DocumentEditor.tsx:72-97, 213, 375` ; `frontend/src/components/Breadcrumb.tsx:24-27` ; `frontend/src/components/MarkdownViewer.tsx:21-34`

## Description

`MarkdownEditor` ne charge `initialContent` qu'**une seule fois** (`loadedRef`), et la route `/ws/:ws/blocs/:bloc/documents/:docId` réutilise la **même instance** de `DocumentEditor` quand seul `docId` change. Le seul remontage possible passe par l'écran « Chargement… » (`isLoading`), qui **ne s'affiche pas si le document cible est frais dans le cache** TanStack (staleTime 30 s). Aggravant : `Breadcrumb.useDocumentChain` fait des `fetchQuery(['document', ws, id])` sur **toute la chaîne d'ancêtres**, pré-remplissant le cache.

## Scénario de reproduction

1. Ouvrir un document parent.
2. Descendre sur un enfant via le panneau enfants.
3. Revenir au parent via le fil d'Ariane (< 30 s).
4. Le titre affiché est celui du parent, mais l'éditeur contient toujours le **contenu de l'enfant** ; `expectedVersion` = version du parent.
5. Une frappe + Ctrl+S → écrit le contenu de l'enfant **dans le parent**, sans conflit.

Même pattern dans `MarkdownViewer` (navigation avant/arrière dans `/pub/:docId`).

## Impact

Corruption croisée de documents : le contenu d'un document est écrit par-dessus un autre, silencieusement. Perte de données.

## Piste de correction

Ajouter `key={docId}` sur `MarkdownEditor` (et une `key` sur `MarkdownViewer`) pour forcer le remontage, ou resynchroniser le contenu quand `initialContent`/`docId` change.
