# AUTH-06 — Race au setup : plusieurs admins créés dans la fenêtre d'init
> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : moyenne
- **Zone** : auth / setup wizard
- **Fichiers** : `backend/src/docflow/setup/service.py:29-39` (`init_admin`)

## Description

`init_admin` vérifie `count==0` puis insère, dans une transaction, mais **sans verrou** ni contrainte « un seul utilisateur ». En READ COMMITTED (défaut), deux requêtes concurrentes lisent toutes deux `count=0` et insèrent chacune un admin avec des `username`/`email` différents : la contrainte d'unicité ne les bloque pas. Deux comptes admin sont créés.

## Scénario de reproduction

1. Instance fraîchement déployée (0 utilisateur).
2. Un attaquant qui « course » l'admin légitime envoie en parallèle `POST /api/setup/init-admin` avec ses propres identifiants.
3. Les deux insertions réussissent → un compte admin pirate persiste.

## Impact

Prise de pied admin sur une instance neuve dans la fenêtre de bootstrap.

## Piste de correction

Sérialiser : `pg_advisory_xact_lock` avant le `count`, ou `SELECT ... FOR UPDATE`, ou un index unique partiel garantissant l'unicité du bootstrap. Fail closed sur la concurrence.
