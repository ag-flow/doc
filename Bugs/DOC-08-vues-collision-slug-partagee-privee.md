# DOC-08 — Vues : collision de slug partagée/privée → résolution indéterminée

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : domaine / vues sauvegardées
- **Fichiers** : `views/service.py:163-182` (`get_view`), `192-223` (`update_view`), `231-244` (`delete_view`) ; migration `0024_saved_views.sql`

## Description

L'unicité est assurée par **deux index partiels distincts** (partagées : `(ws, slug)` ; privées : `(ws, owner, slug)`). Une vue partagée et une vue privée du même slug peuvent donc coexister. `get_view` fait un `fetchrow` sur `(ws, slug, owner IS NULL OR owner = caller)` qui matche les **deux** lignes **sans `ORDER BY`** → ligne renvoyée indéterminée. `update_view`/`delete_view` sélectionnent par `(ws, slug)` seul et peuvent tomber sur la vue privée d'un **autre** utilisateur → 403 erroné, ou modification de « la mauvaise » vue.

## Scénario de reproduction

1. L'utilisateur A a une vue privée `backlog` ; B crée une vue partagée `backlog`.
2. `GET /views/backlog` pour A renvoie aléatoirement l'une ou l'autre.
3. `PATCH /views/backlog` par B peut tomber sur la ligne privée de A → 403 alors que la vue partagée existe.

## Impact

Résolution de vue non déterministe et opérations d'écriture ciblant la mauvaise ligne, y compris entre utilisateurs.

## Piste de correction

Résolution déterministe (priorité privée-du-caller puis partagée, `ORDER BY owner_ref NULLS LAST` + filtre owner dans update/delete), ou interdire la collision de slug à la création.
