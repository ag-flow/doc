# AUTH-04 — Anti-lock-out : dévalidation + COUNT qui ignore `validated`
> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
>
> Hypothèse : le champ `validated` est aussi mutable via `PATCH update_user`, donc le garde
> a été ajouté pour `validated=false` dans `update_user` en plus de `validate_user`, pour
> couvrir le même invariant par tous les chemins.

- **Gravité** : 🟠 MAJEUR (viole une exigence non négociable du projet)
- **Confiance** : haute
- **Zone** : auth / admin users
- **Fichiers** : `backend/src/docflow/auth/lockout.py:8-14` ; `backend/src/docflow/admin/users/service.py:111-121` (`validate_user`)

## Description

Deux défauts liés :

- **(a)** `validate_user(validated=false)` n'appelle **aucun** garde-fou. Or `login` (`auth/router.py:53-54`) et `_resolve_jwt` (`deps.py:47-48`) rejettent tout compte non validé (403 PendingValidation). Dévalider le dernier admin le rend non connectable et invalide ses sessions.
- **(b)** La requête `_COUNT_LOCAL_ADMINS` ne filtre pas sur `validated=true` : elle compte comme « connectables » des admins en réalité non validés. Le garde de disable/delete peut donc conclure à tort qu'un autre admin connectable subsiste.

## Scénario de reproduction

- **(a)** `POST /api/admin/users/{dernier_admin}/unvalidate` → 200, puis plus aucun admin ne peut se connecter.
- **(b)** Deux admins locaux dont un non validé ; désactiver l'admin validé passe le garde (`remaining=1`, le non-validé étant compté) alors qu'aucun admin réellement connectable ne reste.

## Impact

Lock-out irréversible de l'administration, via un chemin non gardé (dévalidation) et un compte de sécurité erroné.

## Piste de correction

Ajouter `AND validated = true` à `_COUNT_LOCAL_ADMINS`, et invoquer `assert_not_last_local_admin` dans le chemin `unvalidate` (`validated=false`) sur le dernier admin.
