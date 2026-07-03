# DEP-04 — L'image de prod tourne en root

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : déploiement / Docker
- **Fichiers** : `deploy/Dockerfile` (aucune directive `USER`)

## Description

Le stage final n'a pas de `USER` ; uvicorn sert le trafic réseau **en root** dans le conteneur. Contraire à la posture « fail closed » du projet.

## Impact

Une compromission de l'app s'exécute avec les privilèges root du conteneur (surface d'escalade accrue).

## Piste de correction

`RUN useradd -r -u 10001 docflow` + `USER docflow` après les `COPY`, avec un répertoire de travail writable pour les dumps temporaires.
