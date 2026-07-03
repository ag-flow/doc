# DEP-09 — Port de dev : la doc dit `:8080`, uvicorn écoute sur 8000

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : déploiement / doc dev
- **Fichiers** : `CLAUDE.md` / `README.md:26` — vs `frontend/vite.config.ts:9`

## Description

La commande documentée `uv run uvicorn docflow.app:app --reload` n'a pas de `--port` → défaut **8000**, mais le commentaire annonce `# :8080`. Le proxy Vite pointe `http://localhost:8000` et est donc **correct de fait** — c'est la doc qui ment. Quiconque « corrige » le proxy vers 8080 en se fiant à la doc casse le dev frontend.

## Impact

Piège de documentation : une « correction » du proxy casse le dev.

## Piste de correction

Soit ajouter `--port 8080` à la commande documentée et aligner le proxy, soit corriger le commentaire en `# :8000`.
