# Déploiement de docflow en production

## Prérequis

- Docker ≥ 24 avec le plugin Compose (`docker compose version`)
- Python 3 disponible sur l'hôte
- Accès à `ghcr.io` (voir § Authentification GHCR si l'image est privée)

---

## Installation — une seule commande

```bash
curl -fsSL https://raw.githubusercontent.com/ag-flow/doc/main/deploy/prod-deploy.sh -o prod-deploy.sh
bash prod-deploy.sh
```

Le script `prod-deploy.sh` effectue automatiquement :

1. Création de `/opt/docflow/` et `/data/`
2. Téléchargement de `docker-compose.prod.yml` (toujours la dernière version depuis `main`)
3. Génération des secrets (`pg_password`, `JWT_SECRET`, `ENCRYPTION_KEY`) et pré-remplissage de `/data/.env`
4. Pause pour que l'opérateur renseigne `ADMIN_EMAIL` et `ADMIN_PASSWORD` dans `/data/.env`
5. Pull de l'image `ghcr.io/ag-flow/doc:latest`
6. Démarrage de la stack (app + postgres)
7. Smoke test sur `/health`

---

## Authentification GHCR (si l'image est privée)

Si le pull échoue avec une erreur d'accès, authentifier Docker auprès de GHCR avant de relancer le script :

1. Créer un **Personal Access Token (PAT)** GitHub avec la permission `read:packages`
   → GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)

2. Se connecter :
   ```bash
   echo "<VOTRE_TOKEN>" | docker login ghcr.io -u <VOTRE_NOM_UTILISATEUR_GITHUB> --password-stdin
   ```

3. Relancer le script :
   ```bash
   bash /opt/docflow/prod-deploy.sh
   ```

---

## Variables de `/data/.env`

Le script pré-remplit automatiquement `DATABASE_URL`, `JWT_SECRET` et `ENCRYPTION_KEY`.  
L'opérateur doit uniquement renseigner :

| Variable | Description |
|---|---|
| `ADMIN_EMAIL` | Email du compte admin bootstrap (accès de secours permanent) |
| `ADMIN_PASSWORD` | Mot de passe fort (≥ 16 caractères) |

Variables optionnelles disponibles dans `/data/.env` :

| Variable | Défaut | Rôle |
|---|---|---|
| `HARPOCRATE_URL` | *(vide)* | URL Harpocrate pour résoudre les `${vault://…}` (automates, OIDC) |
| `AUTOMATION_TICK_SECONDS` | `60` | Intervalle du worker d'automates (secondes) |
| `LOG_LEVEL` | `INFO` | Niveau de log : `DEBUG`, `INFO`, `WARNING`, `ERROR` |

> **`ENCRYPTION_KEY` est critique.** Une fois des données chiffrées en base (wallets, secrets, headers webhook), cette clé ne doit plus jamais changer. La sauvegarder en dehors du serveur.

---

## Mise à jour

```bash
bash /opt/docflow/prod-deploy.sh
```

Le script télécharge la dernière version de `docker-compose.prod.yml`, tire la nouvelle image et redémarre uniquement le conteneur app. Les migrations sont appliquées automatiquement.

---

## Exposition HTTPS

Le service écoute en HTTP sur le port `8080`. Placer un reverse proxy devant.

**Caddy** (TLS automatique Let's Encrypt) :

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

## Sauvegarde

```bash
mkdir -p /data/backups
docker compose -f /opt/docflow/docker-compose.prod.yml exec -T postgres \
  pg_dump -U docflow docflow | gzip > /data/backups/docflow_$(date +%Y%m%d_%H%M).sql.gz
```

Cron quotidien (2h) :

```bash
# crontab -e
0 2 * * * mkdir -p /data/backups && docker compose -f /opt/docflow/docker-compose.prod.yml exec -T postgres pg_dump -U docflow docflow | gzip > /data/backups/docflow_$(date +\%Y\%m\%d_\%H\%M).sql.gz
```

---

## Restauration

```bash
docker compose -f /opt/docflow/docker-compose.prod.yml stop app
gunzip -c /data/backups/docflow_YYYYMMDD_HHMM.sql.gz | \
  docker compose -f /opt/docflow/docker-compose.prod.yml exec -T postgres psql -U docflow -d docflow
docker compose -f /opt/docflow/docker-compose.prod.yml start app
```
