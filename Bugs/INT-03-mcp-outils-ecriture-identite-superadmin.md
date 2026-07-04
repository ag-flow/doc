# INT-03 — Outils MCP d'écriture exécutés sous l'identité du superadmin système
> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
>
> Propagation de l'identité de session MCP implémentée via une `ContextVar`
> (`mcp/server.py`) positionnée par le routeur SSE (`mcp/router.py`) juste avant
> `mcp_server.run`. La boucle de dispatch des messages tourne dans des tâches
> filles héritant de ce contexte, si bien que `create_api_profile` /
> `generate_api_key` utilisent désormais `owner_id = identité authentifiée de
> l'appelant` (fermeture stricte si absente) au lieu du premier superadmin
> système. Chaque connexion SSE vit dans son propre contexte : pas de
> contamination entre sessions concurrentes.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : moyenne
- **Zone** : intégrations / MCP
- **Fichiers** : `backend/src/docflow/mcp/server.py:896-908` (`_system_owner`), `911-947` (`_create_api_profile`), `950-977` (`_generate_api_key`)

## Description

`create_api_profile` et `generate_api_key` via MCP créent des profils/clés attribués à `_system_owner()` (le premier admin local validé), **indépendamment de l'utilisateur qui appelle**. L'accès MCP est gardé par `require_admin`, qui ne vérifie pas `is_admin` (cf. [AUTH-07](AUTH-07-require-admin-ne-verifie-pas-is-admin.md)) : tout utilisateur validé peut donc générer des profils et clés API rattachés au superadmin système, pour n'importe quel workspace.

## Scénario de reproduction

1. Un utilisateur OIDC validé mais non-admin se connecte au SSE MCP.
2. Il appelle `create_api_profile` + `generate_api_key`.
3. Il obtient une clé API valide, **attribuée au compte superadmin**, portée sur un workspace de son choix.

## Impact

Escalade d'attribution/périmètre par rapport au parcours REST (`apikeys` scope les clés à `owner_id` = l'appelant).

## Piste de correction

Propager l'identité authentifiée de la session MCP jusqu'aux outils d'écriture et utiliser cet `owner_id` (et non le premier superadmin), ou restreindre ces outils aux vrais superadmins.
