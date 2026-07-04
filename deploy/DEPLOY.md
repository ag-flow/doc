# Déploiement de docflow

> Ce document couvre la **production** (image GHCR, `prod-deploy.sh`) puis le
> **déploiement dev sur la VM de test** (build local, `./dev-deploy.sh`).

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
4. Pull de l'image `ghcr.io/ag-flow/doc:latest`
5. Démarrage de la stack (app + postgres)
6. Smoke test sur `/health`
7. Création du premier compte admin via le wizard `POST /api/setup/init-admin` (voir § Premier accès)

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

## Premier accès — création du compte admin

Le script pré-remplit automatiquement `DATABASE_URL`, `JWT_SECRET` et `ENCRYPTION_KEY` dans `/data/.env`. Aucun identifiant admin n'est généré ni requis dans ce fichier : il n'existe **aucun bootstrap admin par variable d'environnement**.

Le premier compte admin se crée via le wizard exposé par l'application, tant qu'aucun utilisateur n'existe en base :

```bash
curl -X POST https://docflow.exemple.fr/api/setup/init-admin \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "email": "admin@exemple.fr", "password": "un-mot-de-passe-fort"}'
```

Ce endpoint se désactive automatiquement dès qu'un utilisateur existe (voir `GET /api/setup/status`).

## Variables de `/data/.env`

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

## Déploiement dev (VM de test)

Le script `dev-deploy.sh` vit à la **racine du repo** — geste opérateur homogène
avec les autres repos yoops :

```bash
cd /opt/docflow
sudo ./dev-deploy.sh [BRANCH]     # ex : sudo ./dev-deploy.sh dev
```

Il est idempotent et effectue :

1. **Git sync** : `git fetch` + `checkout [BRANCH]` + `reset --hard origin/[BRANCH]`
   (robuste même quand le script se met à jour lui-même lors de la synchro).
2. **Init/réparation de `/data`** :
   - `/data/pg_password.txt` généré s'il est absent **ou vide** (fichier séparé :
     docker compose le consomme via `secrets:`/`POSTGRES_PASSWORD_FILE`) ;
   - `/data/.env` initialisé par copie de [`deploy/.env.example`](./.env.example)
     s'il est absent — le wizard `init-admin` est rappelé à ce moment ;
   - **réparation clé par clé** : chaque secret manquant ou vide est régénéré
     individuellement (`DATABASE_URL` reconstruite depuis `pg_password.txt`,
     `JWT_SECRET`, `ENCRYPTION_KEY`). Un `.env` partiel est complété, jamais
     écrasé : les valeurs existantes ne sont pas touchées.
3. **Build + redémarrage** : `docker compose build` / `down` / `up -d`.
4. **Smoke test** : `GET /health` (timeout 90 s), échec du script si KO, puis logs.

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

> docflow dispose d'un worker de sauvegarde interne (`backup/worker.py`) qui produit des
> dumps au **format custom** (`pg_dump --format=custom`) et peut les pousser vers
> FTP/FTPS/SFTP — voir l'administration des jobs de sauvegarde dans l'application.
> La procédure ci-dessous est la voie **manuelle** (secours / hors worker), alignée
> sur le même format pour rester compatible avec `pg_restore`.

```bash
mkdir -p /data/backups
docker compose -f /opt/docflow/docker-compose.prod.yml exec -T postgres \
  pg_dump -U docflow --format=custom docflow > /data/backups/docflow_$(date +%Y%m%d_%H%M).dump
```

Le format custom est déjà compressé : pas besoin de `gzip`.

Cron quotidien (2h) :

```bash
# crontab -e
0 2 * * * mkdir -p /data/backups && docker compose -f /opt/docflow/docker-compose.prod.yml exec -T postgres pg_dump -U docflow --format=custom docflow > /data/backups/docflow_$(date +\%Y\%m\%d_\%H\%M).dump
```

---

## Restauration

La restauration **écrase le contenu existant** de la base (`--clean --if-exists`) : elle droppe
chaque objet avant de le recréer, puis s'arrête à la première erreur (`--exit-on-error`) au lieu
de continuer silencieusement sur une base dans un état mélangé.

```bash
docker compose -f /opt/docflow/docker-compose.prod.yml stop app

docker compose -f /opt/docflow/docker-compose.prod.yml exec -T postgres \
  pg_restore -U docflow -d docflow --clean --if-exists --no-owner --exit-on-error \
  < /data/backups/docflow_YYYYMMDD_HHMM.dump
echo "code de sortie pg_restore : $?"
```

Ne redémarrer `app` que si le code de sortie ci-dessus est `0` — une valeur non nulle signale
une restauration incomplète, à ne pas exposer aux utilisateurs :

```bash
docker compose -f /opt/docflow/docker-compose.prod.yml start app
```
