# Outils de génération des captures du guide utilisateur

Régénèrent les images de `docs/images/` sur une **instance de démo éphémère** (jamais sur
une instance réelle). Prérequis : un Chromium browserless accessible en CDP (ex. test1
`:3000`) et `puppeteer-core` (`npm i puppeteer-core` dans un répertoire de travail).

## Procédure

1. Monter l'instance de démo : backend `dev` + frontend buildé (`npm run build`, copier
   `frontend/dist` → `backend/static`) + Postgres jetable. `JWT_SECRET` et
   `ENCRYPTION_KEY` requis ; copier aussi `templates/` (racine du repo) vers
   `backend/templates`. Servir avec `uvicorn --host 0.0.0.0`.
2. Adapter `BROWSER_WS` et `BASE` en tête de `shoot.js`.
3. `node shoot.js setup` — capture du premier démarrage (AVANT toute création de compte).
4. `node shoot.js diagram` — génère l'image de démo `architecture-demo.png`.
5. `bash seed_demo.sh` — crée admin, workspace, types/statuts, blocs, documents, image ;
   affiche les UUID à exporter (`DEMO_FEATURE_DOC`, `DEMO_ARCHI_DOC`, `DEMO_PUB_DOC`).
6. `node shoot.js login` puis `DEMO_...=<uuid> node shoot.js app`, `node shoot.js types`,
   `node shoot.js backup`, `DEMO_PUB_DOC=<uuid> node shoot.js pub`.
7. Copier `shots/*.png` vers `docs/images/`, détruire l'instance de démo.

Les jobs sont indépendants : en cas de timeout de session browserless, relancer seulement
le job manquant (`node shoot.js one <path> <nom>` pour une vue isolée).
