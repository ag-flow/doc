# INT-04 — `POST /api/mcp/messages` sans dépendance d'auth
> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
>
> `POST /mcp/messages` applique désormais la même dépendance `require_admin` que
> le canal SSE (défense en profondeur : un JWT/clé API valide est exigé, plus
> seulement le secret du `session_id`). Couplé à INT-03, l'identité utilisée pour
> les écritures reste celle du propriétaire de la session SSE.
>
> ⚠️ Résiduel documenté : la liaison stricte « message ↔ propriétaire de session »
> du SDK MCP (`_session_owners`) repose sur `scope["user"]` peuplé par le
> middleware d'auth MCP, non branché ici (on utilise les dépendances FastAPI).
> Fermer totalement cette fenêtre imposerait de câbler le middleware Bearer du
> SDK MCP — refonte hors périmètre. La combinaison require_admin + attribution à
> l'identité SSE (INT-03) couvre l'escalade d'attribution et exige un JWT valide.

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute (sur l'absence de contrôle) / moyenne (exploitabilité)
- **Zone** : intégrations / MCP
- **Fichiers** : `backend/src/docflow/mcp/router.py:35-39` (`mcp_messages`) vs `17-32` (`mcp_sse`)

## Description

Le canal SSE (`/mcp/sse`) exige `require_admin`, mais l'endpoint POST qui reçoit **toutes** les invocations d'outils (y compris les écritures) n'a **aucune** dépendance d'auth : il ne repose que sur le secret du `session_id` émis par le transport SSE. La frontière RBAC des écritures MCP n'est donc pas re-vérifiée au niveau du message.

## Scénario de reproduction

Quiconque possède/devine un `session_id` actif peut poster des appels d'outils sans JWT. Les `session_id` sont des UUID non devinables, ce qui limite le risque, mais il n'y a pas de défense en profondeur.

## Impact

Absence de défense en profondeur sur les écritures MCP ; couplé à [AUTH-07](../AUTH-07-require-admin-ne-verifie-pas-is-admin.md) et [INT-03](INT-03-mcp-outils-ecriture-identite-superadmin.md).

## Piste de correction

Appliquer la même dépendance d'auth (ou une vérification de session liée à l'utilisateur authentifié) sur l'endpoint de messages.
