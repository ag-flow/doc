# Roadmap — additif lot 2

> **Ce fichier complète `00_README.md`, il ne le remplace pas.** Convention du corpus,
> identique aux migrations SQL : **on n'édite pas un document poussé, on empile un additif.**
> Quand le modèle sera stable, on consolidera `00` + additifs en un seul index (squash),
> comme on squashera les migrations en un `0001` unique. Pas avant.

## Milestones du lot 2 (dans l'ordre de dépendance)

| #   | Fichier                      | Rôle                                                        | Dépend de            | Migrations |
| --- | ---------------------------- | ---------------------------------------------------------- | -------------------- | ---------- |
| 20  | `20_MT_template_import.md`   | Import de template (héritage, versioning, additif atomique) | M3, M4, M6           | `0002`     |
| 21  | `21_RW_documents_values.md`  | Lecture/écriture contenu + valeurs, versioning, lock optimiste 409 | M1 + `0003`/`0004`/`0005` | `0003`,`0004`,`0005` |
| 22  | `22_MDB_data_block.md`       | Bloc conteneur ; chaînon `document → data_block`           | M3, M4               | `0006`     |
| 23  | `23_MTC_arbre_creation.md`   | Types-enfants autorisés, contrainte miroir serveur, création deux temps, lecture d'arbre | 21, 22, M4 | —          |
| 24  | `24_MUI1_editeur.md`         | Éditeur BlockNote (markdown, mermaid, images) + écran conflit | 21, 23             | —          |
| 25  | `25_MUI2_proprietes.md`      | Panneau de propriétés (component map, états par champ, conflit) | 21, 24           | —          |
| 26  | `26_MUI3_add_liste.md`       | Flux Add + liste/arbre TanStack (colonnes dynamiques, filtre chemin) | 23, 21, 22  | —          |

Ordre d'implémentation conseillé : **20 → 21 → 22 → 23** (backend), puis **24 → 25 → 26** (front).

## État des migrations (empilées)

```
0001_init                          [poussé]
0002_workspace_template_import     [poussé]
0003_document_versioning           [lot 2]
0004_property_value_versioning     [lot 2]
0005_workspace_archive             [lot 2]
0006_document_block_link           [lot 2]  ← chaînon document↔block
```

## Décisions structurantes actées (lot 2)

- Slugs **immuables** partout ; renommage via `label`.
- Base **vierge** : forme finale atteinte au terme des migrations (pas de réécriture du `0001`).
- Versioning = **audit/consultation**, pas de revert pour l'instant (le `version_number` sert au comptage des changements). Revert = ajout futur.
- Contenu et valeurs versionnés **séparément** (axes indépendants) ; conflit **par champ** pour les propriétés.
- Concurrence **optimiste** : `expected_version` → **409 + état courant**, réconciliation **déléguée au code appelant** (jamais de merge serveur).
- Board en **jointure assumée** head→version (redénormaliser seulement si mesuré lent).
- Ré-import template : `label` = maj douce **si version supérieure**, structurel bloquant, no-op à version égale.

## Décisions encore ouvertes

1. **Multi-racines de bloc** (spec 22) : défaut = un bloc = un type racine (zéro migration). Alternative = bloc appliquant le modèle entier avec choix au Add (migration déliant `functional_type_ref`). À trancher.
2. **Archivage du bloc** (spec 22) : `archived_at` sur `data_block` (migration `0007`) ou hard-delete bloqué ?
