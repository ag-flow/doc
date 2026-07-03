# DB-02 — Réconciliation orphelins : suppression massive de workspaces non modifiés

- **Gravité** : 🔴 CRITIQUE
- **Confiance** : haute
- **Zone** : backup / git_sync
- **Fichiers** : `backend/src/docflow/backup/git_sync.py:213-217, 259-267` ; `_find_orphan_files:126-141`

## Description

`existing_slugs` n'est construit que pour les workspaces présents dans `change_rows` (`ws_ids = {row["ws_id"]}`). Mais à l'étape 6, pour un job **sans périmètre** (`workspace_slug` NULL = toute l'instance), `ws_slugs` = **tous** les répertoires du repo. Tout fichier d'un workspace **sans changement dans le batch** a son slug absent de `existing_slugs` → considéré orphelin → `unlink()`, puis commit + push.

Bug secondaire : le matching orphelin se fait par **slug seul** (`p.stem`) sur un set global, alors que les slugs ne sont uniques que **par fratrie** (cf. `0030_document_slug.sql`). Un fichier d'un doc supprimé n'est pas purgé si un autre doc du même slug existe ailleurs ; un doc déplacé laisse un doublon à l'ancien chemin.

## Scénario de reproduction

1. Job de backup global ; workspaces A et B déjà exportés dans le repo git.
2. On modifie un doc de A uniquement.
3. Au run suivant, **tous les `.md`/`.json` de B sont supprimés du repo** et la suppression est **poussée sur le remote**.

## Impact

Perte de données de sauvegarde massive et poussée sur le remote (donc potentiellement propagée aux clones). Destructeur.

## Piste de correction

Réconcilier par **chemin complet** (recalculer les chemins attendus de tous les docs du workspace) et restreindre `ws_slugs` aux workspaces effectivement couverts par `existing_slugs`.
