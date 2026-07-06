# FE-03 — Refetch arrière-plan : verrou optimiste contourné + titre perdu

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
> Le `useEffect` de resync (`DocumentEditor.tsx`) distingue désormais un vrai changement de document (`loadedDocIdRef` != `docId`) d'un refetch d'arrière-plan du même document. Il ne réapplique `title` / `slug` / `expectedVersion` sur un refetch que si `status === 'idle'` : pendant l'édition (`dirty` / `saving` / `error`), la resync est gelée, donc `expectedVersion` reste sur la base de l'utilisateur et un save concurrent produit bien un 409 (dialogue de conflit) au lieu d'un écrasement silencieux. Un titre en cours d'édition n'est plus réinitialisé. Sur un changement de document, la resync est en revanche forcée et `status` remis à `idle`.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : frontend / versioning
- **Fichiers** : `frontend/src/pages/DocumentEditor.tsx:91-97`

## Description

`useEffect([doc])` réapplique `setTitle`, `setSlugValue` et surtout `expectedVersion.current = doc.version` à **chaque refetch** (refetchOnWindowFocus par défaut, staleTime 30 s). Si un autre utilisateur a publié v+1, le refetch aligne `expectedVersion` sur la version serveur alors que l'éditeur contient un contenu basé sur l'ancienne version : la sauvegarde suivante passe **sans 409** et **écrase les modifications concurrentes**. Au passage, un titre en cours d'édition (dirty) est réinitialisé.

## Scénario de reproduction

1. A édite le doc (dirty), change d'onglet > 30 s pendant que B enregistre.
2. A revient (refetch) → `expectedVersion` réaligné sur la version de B.
3. A enregistre → les changements de B sont perdus, sans dialogue de conflit.

## Impact

Le verrou optimiste est contourné par un simple retour d'onglet : perte de modifications concurrentes.

## Piste de correction

Ne pas resynchroniser titre/`expectedVersion` quand `status !== 'idle'` (ou geler le refetch pendant l'édition).
