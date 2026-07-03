# AUTH-09 — Oracle d'énumération d'utilisateurs sur `/auth/login` (timing)

- **Gravité** : 🟡 MINEUR
- **Confiance** : moyenne
- **Zone** : auth / login
- **Fichiers** : `backend/src/docflow/auth/router.py:47-51`

## Description

Si `row is None` (email inexistant) la réponse est immédiate ; si l'email existe, `verify_password` déclenche un hachage argon2 coûteux. La différence de latence permet d'énumérer les emails valides.

## Scénario de reproduction

Mesurer le temps de réponse : ~ms pour email inconnu vs dizaines de ms pour email connu → énumération de comptes.

## Impact

Divulgation de l'existence de comptes (aide au ciblage d'attaques).

## Piste de correction

Effectuer un `verify_password` contre un hash factice constant lorsque `row` est None/sans `password_hash`, pour uniformiser le temps de réponse.
