# DOC-07 — Gardes FK mortes depuis 0011 → suppressions silencieusement destructrices

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute (code mort) / moyenne (intention)
- **Zone** : domaine / properties, blocks, types
- **Fichiers** : `properties/service.py:200-211` (`delete_def`) ; `blocks/service.py:255-272` (`delete_block`) ; `types/service.py:251-262` (`delete_type`) ; migration `0011_type_cascade_delete.sql`

## Description

Ces trois fonctions attrapent `ForeignKeyViolationError` pour renvoyer 409 (« propriété utilisée par des valeurs existantes », « ce bloc a des enfants »), mais la migration 0011 a basculé toutes les FK concernées en `ON DELETE CASCADE` : `properties_values.property_def_ref`, `document.data_block_ref`, `data_block.parent`, `data_block.functional_type_ref`. Les `except` sont donc **du code mort** et les protections annoncées n'existent plus.

La spec `specs/22_MDB_data_block.md` exige pourtant : « Suppression bloquée (RESTRICT) si le bloc contient des documents ».

## Scénario de reproduction

- `DELETE /blocks/{slug}` sur un bloc contenant 500 documents → **suppression silencieuse des 500 docs**, versions, valeurs, références, commentaires (204, aucun avertissement).
- `DELETE /types/{slug}` → cascade types enfants → blocs de ces types → **tous les documents de ces blocs**.
- `DELETE .../properties/{slug}` → toutes les valeurs et leur historique détruits alors que le code prétend renvoyer 409.

## Impact

Perte de données massive et silencieuse via des endpoints qui prétendent (par leur code de gestion d'erreur) être protégés.

## Piste de correction

Soit assumer la cascade et retirer les `except` morts + ajouter une confirmation applicative (compter les dépendants, exiger `confirm`), soit revenir à RESTRICT sur `document.data_block_ref` et `properties_values.property_def_ref` (migration explicite) conformément à la spec 22. Rappel `LESSONS.md` : une migration délibérée ne se « corrige » pas en réintroduisant l'ancien comportement — trancher côté architecte.
