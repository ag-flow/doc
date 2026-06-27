# Déploiement de docflow en production

## Prérequis

- Docker ≥ 24 avec le plugin Compose (`docker compose version`)
- Un compte GitHub membre de l'organisation `ag-flow` (l'image GHCR est privée)
- Python 3 disponible sur l'hôte (génération des secrets)

---

## Étape 1 — Récupérer les fichiers de déploiement

Cloner le dépôt sur la machine de production :

```bash
git clone git@github.com:ag-flow/doc.git /opt/docflow
cd /opt/docflow
```

> Si git n'est pas disponible, copier au minimum ces deux fichiers depuis un poste ayant accès au dépôt :
> - `deploy/docker-compose.prod.yml`
> - `deploy/.env.example`

---

## Étape 2 — S'authentifier sur GitHub Container Registry

L'image Docker est hébergée sur GHCR (privé). Il faut un **Personal Access Token (PAT)** GitHub avec la permission `read:packages`.

### Créer le PAT (une seule fois)

1. Aller sur GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)**
2. Générer un token avec la permission **`read:packages`** cochée
3. Copier le token

### Se connecter à GHCR sur la machine de production

```bash
echo "<VOTRE_TOKEN>" | docker login ghcr.io -u <VOTRE_NOM_UTILISATEUR_GITHUB> --password-stdin
```

Vérification :

```bash
# Doit afficher "Login Succeeded"
```

---

## Étape 3 — Créer le répertoire des secrets

```bash
mkdir -p /data
chmod 700 /data
```

---

## Étape 4 — Mot de passe PostgreSQL

```bash
python3 -c "import secrets; print(secrets.token_hex(24))" > /data/pg_password.txt
chmod 600 /data/pg_password.txt
cat /data/pg_password.txt   # noter ce mot de passe
```

---

## Étape 5 — Fichier de configuration

```bash
cp /opt/docflow/deploy/.env.example /data/.env
chmod 600 /data/.env
```

Éditer `/data/.env` et renseigner les variables suivantes :

### `DATABASE_URL`

Remplacer `CHANGE_ME` par le mot de passe généré à l'étape 4 :

```
DATABASE_URL=postgresql://docflow:<contenu de /data/pg_password.txt>@postgres:5432/docflow
```

### `JWT_SECRET`

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Coller la valeur dans `.env` :
```
JWT_SECRET=<valeur générée>
```

### `ADMIN_EMAIL` et `ADMIN_PASSWORD`

Compte administrateur de secours, accessible même si l'OIDC est configuré :

```
ADMIN_EMAIL=admin@exemple.fr
ADMIN_PASSWORD=<mot de passe fort, 16 caractères minimum>
```

### `ENCRYPTION_KEY`

Nécessaire pour chiffrer les secrets vault, wallets et headers. **Ne jamais changer cette valeur une fois des données chiffrées en base.**

```bash
python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

```
ENCRYPTION_KEY=<valeur générée>
```

> **Sauvegarder `ENCRYPTION_KEY` en dehors du serveur** (gestionnaire de mots de passe, coffre-fort). La perdre rend illisibles tous les secrets stockés.

---

## Étape 6 — Démarrage

```bash
cd /opt/docflow
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml up -d
```

### Vérifier que tout est prêt

```bash
until curl -sf http://localhost:8080/health; do echo "En attente…"; sleep 3; done
echo "docflow est démarré"
```

Les migrations SQL sont appliquées automatiquement au premier démarrage. Le compte admin bootstrap est créé à ce moment.

### Consulter les logs

```bash
docker compose -f deploy/docker-compose.prod.yml logs -f app
```

---

## Mise à jour

```bash
cd /opt/docflow
git pull --ff-only origin main
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml up -d --no-deps app
```

Le `--no-deps app` redémarre uniquement le conteneur applicatif. Les nouvelles migrations sont appliquées automatiquement.

---

## Exposition HTTPS

Le service écoute en HTTP sur le port `8080`. Placer un reverse proxy devant pour HTTPS.

**Caddy** (recommandé — TLS automatique via Let's Encrypt) :

```
docflow.exemple.fr {
    reverse_proxy localhost:8080
}
```

**Nginx** :

```nginx
server {
    listen 443 ssl;
    server_name docflow.exemple.fr;
    ssl_certificate     /etc/letsencrypt/live/docflow.exemple.fr/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/docflow.exemple.fr/privkey.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Sauvegarde de la base de données

```bash
mkdir -p /data/backups
docker compose -f deploy/docker-compose.prod.yml exec postgres \
  pg_dump -U docflow docflow | gzip > /data/backups/docflow_$(date +%Y%m%d_%H%M).sql.gz
```

Exemple de cron quotidien (2h du matin) :

```bash
# crontab -e
0 2 * * * mkdir -p /data/backups && docker compose -f /opt/docflow/deploy/docker-compose.prod.yml exec -T postgres pg_dump -U docflow docflow | gzip > /data/backups/docflow_$(date +\%Y\%m\%d_\%H\%M).sql.gz
```

---

## Restauration

```bash
# Arrêter l'app (pas la base)
docker compose -f deploy/docker-compose.prod.yml stop app

# Restaurer
gunzip -c /data/backups/docflow_YYYYMMDD_HHMM.sql.gz | \
  docker compose -f deploy/docker-compose.prod.yml exec -T postgres \
  psql -U docflow -d docflow

# Relancer
docker compose -f deploy/docker-compose.prod.yml start app
```

---

## Variables optionnelles

| Variable | Défaut | Rôle |
|---|---|---|
| `HARPOCRATE_URL` | *(vide)* | URL du service Harpocrate pour résoudre les références `${vault://…}` dans les automates et l'OIDC |
| `AUTOMATION_TICK_SECONDS` | `60` | Intervalle en secondes entre chaque vérification du worker d'automates |
| `LOG_LEVEL` | `INFO` | Niveau de log : `DEBUG`, `INFO`, `WARNING`, `ERROR` |
