# 02b — Errata : valeurs & contenu en tables de version (head → version → item)

> **Additif à `02_DATA_MODEL.md`** — on empile, on ne réécrit pas. `02` décrit la forme **initiale** (`0001`) ; les migrations de versioning l'ont fait évoluer. Ce fichier acte l'état réel et sert de référence pour toute spec touchant aux valeurs ou au contenu.

## Ce qui a changé depuis `02`

`02_DATA_MODEL` montre `document.contenu` et `properties_values.value` / `.allowed_value_ref` **sur les tables principales**. Ce n'est **plus** le cas.

### Contenu des documents (`0003`/`0004`)

- `document` est devenu une **tête** : garde `title` (dénormalisé, arbre à plat) + `version` (numéro courant). **`contenu` a été retiré.**
- Le corps vit dans **`document_version.content`** (`document_ref`, `version_number`, `content`, `created_at`).
- Lecture du corps courant : `WHERE document_ref = D AND version_number = document.version`.

### Valeurs de propriété (`0004`/`0005`)

- `properties_values` est devenu une **tête d'identité pure** : `id, document_ref, property_def_ref, version, workspace_technical_key`, `UNIQUE(document_ref, property_def_ref)`. **`value` et `allowed_value_ref` ont été retirés.**
- La valeur vit dans **`properties_value_version`** (`version_technical_key`, `property_value_ref`, `version_number`, `value`, `allowed_value_ref`, `CHECK` value⊕allowed_value_ref).
- Lecture de la valeur courante : jointure head → version sur `version_number = head.version`.

### Évolution à venir (`38_MREL`, `39_MMV`)

- `38_MREL` ajoute `target_document_ref` (FK molle) sur **`properties_value_version`** + élargit le `CHECK` à `num_nonnulls(value, allowed_value_ref, target_document_ref) <= 1`.
- `39_MMV` descend les **trois** colonnes porteuses (`value`, `allowed_value_ref`, `target_document_ref`) d'un cran dans **`properties_value_item`** (`version_ref`, `position`, …). Une version = un **instantané de liste** ; mono = liste à 1 item. `properties_defs` gagne `max_occurrences` (défaut 1).

## Chaîne de lecture cible (après `39`)

```
properties_values (head: identité + version)
  → properties_value_version (instantané numéroté)
    → properties_value_item   (items ordonnés : value | allowed_value_ref | target_document_ref)
```

```sql
SELECT i.position, i.value, i.allowed_value_ref, i.target_document_ref
FROM   properties_values pv
JOIN   properties_value_version pvv
       ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
JOIN   properties_value_item i
       ON i.version_ref = pvv.version_technical_key
WHERE  pv.document_ref = $1 AND pv.property_def_ref = $2
ORDER  BY i.position;       -- 1 ligne en mono, N en multi
```

## Invariants mis à jour

- L'invariant « `value` XOR `allowed_value_ref` » (I-3 de `02`) est désormais porté par **`properties_value_version`** (puis l'**item** après `39`), pas par `properties_values`.
- Le `UNIQUE(document_ref, property_def_ref)` sur le head **reste** (un head par couple) — la multi-valeur ne le touche pas (elle vit sous la version, dans les items).

## Specs concernées

`34_MPTS`, `35_MTPL`, `36_MEXP`, `37_MVIEW`, `38_MREL`, `39_MMV` — toutes alignées sur cette chaîne. Toute nouvelle spec touchant valeur/contenu doit lire **head → version (→ item)**, jamais une colonne de valeur sur le head.
