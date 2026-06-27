# Déploiement de docflow en production

## Prérequis

- Docker ≥ 24 avec le plugin Compose (`docker compose version`)
- Accès à `ghcr.io` (aucun compte requis pour les images publiques)
- Un répertoire `/data/` sur l'hôte pour les fichiers secrets (hors git)

---

## Première installation

### 1. Créer le répertoire de secrets

```bash
mkdir -p /data
chmod 700 /data
```

### 2. Mot de passe PostgreSQL

```bash
# Générer un mot de passe aléatoire
python3 -c "import secrets; print(secrets.token_hex(24))" > /data/pg_password.txt
chmod 600 /data/pg_password.txt
```

### 3. Fichier `.env`

```bash
cp deploy/.env.example /data/.env
chmod 600 /data/.env
```

Ouvrir `/data/.env` et remplir **toutes les valeurs REQUIS** :

| Variable | Comment générer |
|---|---|
| `DATABASE_URL` | Remplacer `CHANGE_ME` par le contenu de `/data/pg_password.txt` |
| `JWT_SECRET` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_EMAIL` | Adresse email du compte admin break-glass |
| `ADMIN_PASSWORD` | Mot de passe fort (≥ 16 caractères) |
| `ENCRYPTION_KEY` | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

> ⚠️ **`ENCRYPTION_KEY` est critique.** Une fois utilisée pour chiffrer des données (wallets, secrets, headers webhook), elle ne doit plus jamais changer. Sauvegarder cette valeur en dehors du serveur (gestionnaire de mots de passe, coffre-fort).

### 4. Récupérer l'image et démarrer

```bash
# Se positionner à la racine du dépôt (ou copier docker-compose.prod.yml)
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml up -d
```

### 5. Vérifier le démarrage

```bash
# Health check (attend que l'app soit prête)
until curl -sf http://localhost:8080/health; do echo "En attente…"; sleep 3; done
echo "docflow est démarré"

# Voir les logs
docker compose -f deploy/docker-compose.prod.yml logs -f app
```

Les migrations SQL sont appliquées **automatiquement** au démarrage. Le compte admin bootstrap est créé à ce moment si absent.

---

## Mise à jour

```bash
# Récupérer la nouvelle image
docker compose -f deploy/docker-compose.prod.yml pull

# Redémarrer sans interruption de la base
docker compose -f deploy/docker-compose.prod.yml up -d --no-deps app
```

Les migrations nouvelles sont appliquées automatiquement au redémarrage de l'app (runner idempotent).

---

## Sauvegarde de la base

```bash
# Dump compressé
docker compose -f deploy/docker-compose.prod.yml exec postgres \
  pg_dump -U docflow docflow | gzip > /data/backups/docflow_$(date +%Y%m%d_%H%M).sql.gz
```

---

## Variables optionnelles

Voir les commentaires dans `deploy/.env.example` pour :
- `HARPOCRATE_URL` — résolution des secrets `${vault://…}` (automates, OIDC)
- `AUTOMATION_TICK_SECONDS` — cadence du worker d'automates (défaut : 60 s)
- `LOG_LEVEL` — niveau de verbosité des logs (défaut : `INFO`)

---

## Accès au service

Par défaut : `http://<IP_SERVEUR>:8080`

Pour exposer en HTTPS, placer un reverse proxy (Caddy, Nginx, Traefik) devant le port 8080. Exemple Caddy minimal :

```
docflow.example.com {
    reverse_proxy localhost:8080
}
```
