# FE-03 — Refetch arrière-plan : verrou optimiste contourné + titre perdu

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
