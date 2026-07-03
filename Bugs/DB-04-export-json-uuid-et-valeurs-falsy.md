# DB-04 — Export JSON : `TypeError` sur UUID + valeurs falsy écrasées

- **Gravité** : 🔴 CRITIQUE (fait échouer tout le run)
- **Confiance** : haute
- **Zone** : backup / git_sync
- **Fichiers** : `backend/src/docflow/backup/git_sync.py:60, 103-109`

## Description

```python
doc["properties"] = {slug: r["value"] or r["allowed_value_ref"]}
```

- Pour une propriété `restricted_list`, `value` est NULL et `allowed_value_ref` est un `uuid.UUID` → `json.dumps(meta)` (sans `default=`) lève **`TypeError: Object of type UUID is not JSON serializable`**.
- `value or ...` : une valeur texte `""` ou `"0"` (int 0 / bool false stockés en texte) retombe sur `allowed_value_ref` (None) → **valeur perdue**.

## Scénario de reproduction

- Un seul document du batch porte un statut (restricted_list) → **le run git_sync entier échoue** (`TypeError`).
- Un doc avec propriété int `0` est exporté avec `null`.

## Impact

Toute instance utilisant des statuts (donc la quasi-totalité) voit ses sauvegardes git_sync échouer systématiquement dès qu'un doc avec statut est dans le batch.

## Piste de correction

Joindre `properties_allowed_values` pour exporter le **slug** de la valeur autorisée (pas l'UUID interne), et tester `is not None` au lieu du `or`.
