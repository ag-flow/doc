# DOC-14 — Incohérences domaine diverses (groupées)

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus. Les 4 sous-correctifs sont appliqués :
> 1. Helper `compute_initial_content` factorisé (template_apply) et utilisé par
>    `create_document` et `create_document_in_block`.
> 2. `resolve_view` charge `limit+1` et expose `has_more` (troncature signalée) ;
>    pagination cursor complète non implémentée (option « au minimum has_more » retenue).
> 3. `create_view` valide l'appartenance de `bloc_ref` au workspace (422 sinon).
> 4. `update_def` distingue champ absent / champ = null → `default_value` peut être
>    remis à NULL (label/required NOT NULL restent protégés).

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : domaine / documents, vues, properties

Regroupe quatre incohérences mineures constatées lors de l'audit.

## 1. `content_template` non appliqué dans `create_document_in_block`

`create_document_in_block` (`block_ops.py:411-416`) n'applique **pas** le `content_template` du type, alors que `create_document` (`service.py:230-234`) le fait. Un document créé via un bloc n'obtient pas son modèle de contenu.
→ **Piste** : factoriser l'application du template dans les deux chemins.

## 2. Pagination des vues non implémentée (troncature silencieuse)

`resolve_view` accepte un paramètre `cursor` **jamais utilisé** ; `next_cursor` est toujours `None` (`views/service.py:254, 361`). Les vues au-delà de `limit` **tronquent silencieusement** sans indiquer qu'il y a une suite.
→ **Piste** : implémenter la pagination par cursor, ou au minimum signaler `has_more`.

## 3. `saved_view.bloc_ref` sans FK ni validation

`saved_view.bloc_ref` n'a **pas de FK** (`0024`) et n'est **pas validé** à la création (`views/service.py:105-139`) : un `bloc_ref` inexistant ou d'un autre workspace donne une vue qui résout **toujours vide**, sans erreur.
→ **Piste** : valider l'appartenance du `bloc_ref` au workspace à la création.

## 4. `update_def` ne peut pas remettre `default_value` à NULL

`update_def` filtre `v is not None` (`properties/service.py:181`) : il est **impossible** de remettre à NULL `default_value` via l'API (on ne peut que le changer vers une autre valeur non nulle).
→ **Piste** : distinguer « champ absent » de « champ = null » (utiliser un sentinel `UNSET`).
