# DEP-01 — Identifiants admin bootstrap morts affichés par le déploiement

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : déploiement / doc
- **Fichiers** : `scripts/dev-deploy.sh:52-69` ; `scripts/.env.example:11-13` ; `deploy/DEPLOY.md:23, 54-57`

## Description

`auth/seed.py` ne contient plus que le commentaire « Bootstrap par variable d'environnement supprimé. Le premier compte admin est créé via le wizard ». Aucun code ne lit `ADMIN_EMAIL`/`ADMIN_PASSWORD` et `Settings` ne déclare pas ces champs. Pourtant `dev-deploy.sh` les génère, les écrit dans `/data/.env` et affiche un encadré « Identifiants bootstrap admin » ; `scripts/.env.example` les présente comme requis ; `DEPLOY.md` affirme que le script prod « fait une pause pour renseigner ADMIN_EMAIL et ADMIN_PASSWORD » — alors que `prod-deploy.sh` ne fait aucune pause.

## Scénario de reproduction

1. Opérateur déploie sur test1, note les identifiants affichés.
2. Tente de se connecter → **échec**, aucun admin n'existe (confirmé par l'état réel de test1 : aucun admin bootstrapé).

## Impact

Doc/scripts trompeurs : l'opérateur croit avoir un compte admin, il n'en a pas et ne sait pas qu'il doit passer par le wizard.

## Piste de correction

Purger `ADMIN_*` de `dev-deploy.sh`, `scripts/.env.example` et `DEPLOY.md` ; remplacer l'encadré par un pointeur vers le wizard `POST /api/setup/init-admin`.
