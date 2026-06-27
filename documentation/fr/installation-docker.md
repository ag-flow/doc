# Installation avec Docker — docflow

Cette méthode est recommandée pour la production. Elle utilise l'image pré-construite disponible sur GitHub Container Registry (GHCR).

## Prérequis

- Docker ≥ 24 avec le plugin Compose (`docker compose version`)
- Python 3 disponible sur l'hôte (pour générer les secrets)
- Accès réseau à `ghcr.io`

---

## Étape 1 — Récupérer les fichiers de déploiement

Cloner le dépôt ou copier uniquement les fichiers nécessaires :

```bash
git clone git@github.com:ag-flow/doc.git /opt/docflow
cd /opt/docflow
```

Les deux fichiers utilisés sont :
- `deploy/docker-compose.prod.yml` — définition des services
- `deploy/.env.example` — modèle de configuration

---

## Étape 2 — Créer le répertoire des secrets

```bash
mkdir -p /data
chmod 700 /data
```

Ce répertoire contient les fichiers de secrets. Il ne doit jamais être commité ni sauvegardé sans chiffrement.

---

## Étape 3 — Mot de passe PostgreSQL

```bash
python3 -c "import secrets; print(secrets.token_hex(24))" > /data/pg_password.txt
chmod 600 /data/pg_password.txt
```

Retenir ce mot de passe — il sera utilisé dans `DATABASE_URL`.

---

## Étape 4 — Fichier de configuration

```bash
cp deploy/.env.example /data/.env
chmod 600 /data/.env
```

Ouvrir `/data/.env` et renseigner les valeurs suivantes :

### DATABASE_URL

```
DATABASE_URL=postgresql://docflow:<contenu de /data/pg_password.txt>@postgres:5432/docflow
```

Remplacer `<contenu de /data/pg_password.txt>` par la valeur générée à l'étape 3.

### JWT_SECRET

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copier la valeur dans `/data/.env` :

```
JWT_SECRET=<valeur générée>
```

### ADMIN_EMAIL et ADMIN_PASSWORD

Compte administrateur de secours, toujours accessible même si OIDC est configuré.

```
ADMIN_EMAIL=admin@exemple.fr
ADMIN_PASSWORD=<mot de passe fort, 16 caractères minimum>
```

### ENCRYPTION_KEY

Nécessaire pour chiffrer les secrets vault, les wallets Harpocrate et les headers de webhook.

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```
ENCRYPTION_KEY=<valeur générée>
```

> **Important :** une fois que des données ont été chiffrées avec cette clé, ne plus jamais la changer. Sauvegarder cette valeur dans un gestionnaire de mots de passe ou un coffre-fort séparé de l'environnement de production.

---

## Étape 5 — Démarrage

```bash
cd /opt/docflow
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml up -d
```

### Vérifier que tout est démarré

```bash
until curl -sf http://localhost:8080/health; do echo "En attente…"; sleep 3; done
echo "docflow est prêt"
```

Les migrations SQL sont appliquées automatiquement au premier démarrage. Le compte admin est créé à ce moment.

### Consulter les logs

```bash
docker compose -f deploy/docker-compose.prod.yml logs -f app
```

---

## Mise à jour

À chaque nouvelle version (merge sur `main` du dépôt GitHub), une nouvelle image est publiée automatiquement sur GHCR.

```bash
cd /opt/docflow
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml up -d --no-deps app
```

Le `--no-deps app` redémarre uniquement le conteneur applicatif sans toucher à la base de données. Les migrations éventuellement nouvelles sont appliquées automatiquement au démarrage.

---

## Exposition HTTPS

Le service écoute sur le port `8080` en HTTP. Pour le rendre accessible en HTTPS, placer un reverse proxy devant.

**Exemple avec Caddy** (auto-TLS Let's Encrypt) :

```
docflow.exemple.fr {
    reverse_proxy localhost:8080
}
```

**Exemple avec Nginx** :

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

Programmer cette commande dans un cron quotidien et copier les dumps sur un stockage externe.

---

## Restauration

```bash
# Arrêter l'app pendant la restauration
docker compose -f deploy/docker-compose.prod.yml stop app

# Restaurer
gunzip -c /data/backups/docflow_YYYYMMDD_HHMM.sql.gz | \
  docker compose -f deploy/docker-compose.prod.yml exec -T postgres \
  psql -U docflow docflow

# Relancer
docker compose -f deploy/docker-compose.prod.yml start app
```

---

## Variables optionnelles

| Variable | Défaut | Rôle |
|---|---|---|
| `HARPOCRATE_URL` | *(vide)* | URL du service Harpocrate pour résoudre `${vault://…}` |
| `AUTOMATION_TICK_SECONDS` | `60` | Intervalle du worker d'automates (secondes) |
| `LOG_LEVEL` | `INFO` | Niveau de log : `DEBUG`, `INFO`, `WARNING`, `ERROR` |
