# AUTH-03 — Anti-lock-out contourné : démotion `is_admin` du dernier admin
> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.

- **Gravité** : 🟠 MAJEUR (viole une exigence non négociable du projet)
- **Confiance** : haute
- **Zone** : auth / admin users
- **Fichiers** : `backend/src/docflow/admin/users/service.py:86-104` (`update_user`)

## Description

`assert_not_last_local_admin` n'est appelé que si `updates.get('disabled') is True`. Le changement `is_admin=false` n'est **pas gardé**. Un superadmin peut retirer `is_admin` au dernier admin local, laissant **zéro admin** connectable.

CLAUDE.md : « le dernier admin local connectable par mot de passe ne peut être ni désactivé ni supprimé. C'est un **test**, pas une intention. »

## Scénario de reproduction

1. `PATCH /api/admin/users/{id_dernier_admin}` avec `{"is_admin": false}`.
2. Aucun garde-fou ne se déclenche, l'UPDATE passe.
3. Plus personne ne satisfait `require_superadmin` → gestion des utilisateurs et config OIDC **verrouillées définitivement**.

## Impact

Auto-lock-out irréversible de l'administration de l'instance.

## Piste de correction

Appeler `assert_not_last_local_admin` aussi quand `updates` contient `is_admin=false` (et toute mutation retirant la qualité d'admin local connectable), dans la même transaction. Voir aussi [AUTH-04](AUTH-04-anti-lockout-devalidation-et-count.md).
