# DOC-01 — Renumérotation des placeholders `$n` cassée dans le moteur de vues

- **Gravité** : 🔴 CRITIQUE
- **Confiance** : haute (reproduit par exécution + relecture directe)
- **Zone** : domaine / vues sauvegardées
- **Fichiers** : `backend/src/docflow/views/service.py:304-309` ; `backend/src/docflow/views/filter_engine.py:130-151, 232-243`

## Description

`resolve_view` décale les placeholders du filtre avec :

```python
offset = 2
for i, _p in enumerate(filter_params, start=1):
    filter_sql = filter_sql.replace(f"${i}", f"${i + offset}", 1)
```

Deux défauts distincts :

1. **Cascade de renommage** : `$1 → $3`, puis à l'itération `i=3` le `replace` retombe sur le `$3` **fraîchement créé** (première occurrence dans la chaîne) et le renomme en `$5`. Avec 3 prédicats `contains` `[a, b, c]`, les clauses reçoivent `$5, $4, $3` au lieu de `$3, $4, $5` → **les valeurs `a` et `c` sont permutées silencieusement**. Le problème `$1` préfixe de `$10` (déjà noté dans `LESSONS.md`) s'y ajoute au-delà de 9 paramètres.
2. **Occurrences dupliquées** : les opérateurs `is`, `is_not`, `in` réutilisent le même placeholder deux fois (`pvv2.value = $2 OR pav2.slug = $2`). Le `replace(..., 1)` ne renumérote **que la première occurrence**. Pour un seul prédicat `is` : `... pd2.slug = $3 AND (pvv2.value = $4 OR pav2.slug = $2)` — le `$2` résiduel pointe sur `bloc_ref` (uuid) → erreur de type Postgres 500.

## Scénario de reproduction

- Vue sauvegardée `filter: [{"field":"status","op":"is","value":"open"}]` → `GET /views/{slug}/resolve` → **500** (uuid vs text).
- Vue avec 3 filtres `contains` → **résultats faux sans erreur** (valeurs permutées).

## Impact

Le moteur de vues sauvegardées est inutilisable dès qu'un filtre non trivial est appliqué : soit 500, soit résultats silencieusement faux (fiabilité des tableaux/boards compromise).

## Piste de correction

Ne jamais renuméroter par `str.replace`. Instancier `FilterBuilder` avec un offset de départ (les `$n` sont émis directement décalés), ou renuméroter via une regex `\$(\d+)\b` en une seule passe avec une fonction de remplacement.
