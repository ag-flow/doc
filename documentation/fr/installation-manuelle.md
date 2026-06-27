# Installation manuelle — docflow

Cette méthode installe docflow directement sur l'hôte, sans Docker. Elle convient aux environnements où Docker n'est pas disponible ou non souhaité.

## Prérequis

| Composant | Version minimale | Vérification |
|---|---|---|
| Python | 3.12 | `python3 --version` |
| uv | dernière | `uv --version` |
| Node.js | 20 LTS | `node --version` |
| npm | 10+ | `npm --version` |
| PostgreSQL | 13 | `psql --version` |

### Installer uv (gestionnaire Python)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### Installer Node.js (si absent)

```bash
# Via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
```

---

## Étape 1 — Cloner le dépôt

```bash
git clone git@github.com:ag-flow/doc.git /opt/docflow
cd /opt/docflow
```

---

## Étape 2 — Créer la base de données PostgreSQL

Se connecter à PostgreSQL en tant que super-utilisateur :

```bash
sudo -u postgres psql
```

Dans le shell psql :

```sql
CREATE USER docflow WITH PASSWORD 'MOT_DE_PASSE_CHOISI';
CREATE DATABASE docflow OWNER docflow;
\q
```

Retenir le mot de passe — il sera utilisé dans `DATABASE_URL`.

---

## Étape 3 — Construire le frontend

```bash
cd /opt/docflow/frontend
npm ci
npm run build
# Les assets sont générés dans frontend/dist/
```

---

## Étape 4 — Installer les dépendances Python

```bash
cd /opt/docflow/backend
uv sync --no-dev --frozen
```

---

## Étape 5 — Fichier de configuration

Créer `/opt/docflow/.env` (ou `/data/.env`, le chemin peut être ajusté) :

```bash
cp deploy/.env.example /opt/docflow/.env
chmod 600 /opt/docflow/.env
```

Renseigner les variables :

```bash
# Base de données
DATABASE_URL=postgresql://docflow:MOT_DE_PASSE_CHOISI@localhost:5432/docflow

# JWT — générer avec :
# python3 -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=<valeur générée>

# Compte admin bootstrap
ADMIN_EMAIL=admin@exemple.fr
ADMIN_PASSWORD=<mot de passe fort>

# Chiffrement — générer avec :
# python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=<valeur générée>

LOG_LEVEL=INFO
```

---

## Étape 6 — Copier les assets frontend dans le dossier static

L'application sert les fichiers statiques depuis `backend/static/`. Copier le build :

```bash
cp -r /opt/docflow/frontend/dist /opt/docflow/backend/static
```

---

## Étape 7 — Appliquer les migrations

Les migrations SQL sont appliquées par le runner intégré à l'application. Définir la variable d'environnement avant de lancer :

```bash
cd /opt/docflow/backend
export $(grep -v '^#' /opt/docflow/.env | xargs)
uv run python -m docflow.db.apply
```

Cette commande est idempotente : elle peut être rejouée sans effet si les migrations ont déjà été appliquées.

---

## Étape 8 — Lancer l'application

```bash
cd /opt/docflow/backend
export $(grep -v '^#' /opt/docflow/.env | xargs)
uv run uvicorn docflow.app:app --host 0.0.0.0 --port 8080
```

Vérifier le démarrage :

```bash
curl http://localhost:8080/health
# Réponse attendue : {"status":"ok"}
```

---

## Service systemd (démarrage automatique)

Créer `/etc/systemd/system/docflow.service` :

```ini
[Unit]
Description=docflow
After=network.target postgresql.service

[Service]
Type=simple
User=docflow
WorkingDirectory=/opt/docflow/backend
EnvironmentFile=/opt/docflow/.env
ExecStart=/opt/docflow/backend/.venv/bin/uvicorn docflow.app:app --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Activer et démarrer le service :

```bash
# Créer un utilisateur système dédié
useradd -r -s /sbin/nologin -d /opt/docflow docflow
chown -R docflow:docflow /opt/docflow

systemctl daemon-reload
systemctl enable --now docflow
systemctl status docflow
```

---

## Mise à jour manuelle

```bash
cd /opt/docflow

# 1. Récupérer les changements
git pull --ff-only origin main

# 2. Mettre à jour les dépendances Python
cd backend && uv sync --no-dev --frozen && cd ..

# 3. Reconstruire le frontend
cd frontend && npm ci && npm run build
cp -r dist /opt/docflow/backend/static
cd ..

# 4. Appliquer les nouvelles migrations
cd backend
export $(grep -v '^#' /opt/docflow/.env | xargs)
uv run python -m docflow.db.apply

# 5. Redémarrer le service
systemctl restart docflow
```

---

## Exposition HTTPS

Même principe que pour l'installation Docker : placer Caddy ou Nginx en reverse proxy devant le port 8080.

```
docflow.exemple.fr {
    reverse_proxy localhost:8080
}
```

---

## Sauvegarde de la base

```bash
mkdir -p /data/backups
pg_dump -U docflow docflow | gzip > /data/backups/docflow_$(date +%Y%m%d_%H%M).sql.gz
```
