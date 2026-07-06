# DEP-08 — `prod-deploy.sh` source le `.env` format docker dans bash

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : déploiement / script
- **Fichiers** : `deploy/prod-deploy.sh:77`

## Description

`set -a; source "$DATA/.env"; set +a` — un fichier `env_file` docker (valeurs brutes, non quotées) est interprété par **bash**. Une valeur contenant espace, `$`, backtick ou `#` est valide pour docker mais casse le script — au mieux erreur, au pire **exécution de contenu** du `.env`.

## Scénario de reproduction

1. Un mot de passe avec un espace dans `/data/.env`.
2. Le conteneur démarre correctement, mais tout redéploiement via `prod-deploy.sh` échoue à l'étape « Configuration validée ».

## Impact

Redéploiement cassé et risque d'exécution de contenu de `.env`.

## Piste de correction

Valider les clés requises par parsing ligne à ligne (`grep -E '^JWT_SECRET=.+'`) au lieu de sourcer le fichier.
