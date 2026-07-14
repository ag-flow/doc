# Déploiement de docflow

> Ce document couvre la **production** (image GHCR, `prod-deploy.sh`) puis le
> **déploiement dev sur la VM de test** (build local, `./dev-deploy.sh`).

## Prérequis

- Docker ≥ 24 avec le plugin Compose (`docker compose version`)
- Python 3 disponible sur l'hôte
- Accès à `ghcr.io` (voir § Authentification GHCR si l'image est privée)

---

## Procédure complète — mise en place d'une instance de production

Checklist dans l'ordre. Chaque étape renvoie vers le paragraphe détaillé plus bas.

### 1. Publier l'image (dev → main)

Le pipeline `.github/workflows/build-and-push.yml` ne construit et ne publie
l'image que sur push vers `main`. Rien ne se déploie tant que ce merge n'a pas
eu lieu.

```bash
git checkout main && git pull origin main
git merge --ff-only origin/dev   # ou merge classique si main a divergé
git push origin main
```

Suivre le run sur GitHub Actions : il publie `ghcr.io/ag-flow/doc:latest` et
`ghcr.io/ag-flow/doc:sha-<court>`. **Ne pas lancer l'étape 4 avant que ce build
soit vert.**

### 2. Provisionner la machine

- VM Linux x86_64 ou arm64, Docker ≥ 24 + plugin Compose, accès sortant à
  `ghcr.io`.
- Dimensionnement minimal : 1 vCPU / 1 Go RAM pour app + Postgres en usage
  léger ; à ajuster selon le volume de documents/artefacts stockés.
- Créer l'enregistrement DNS `docflow.yoops.org` → IP de la VM.
- Ouvrir les ports 80/443 en entrée pour le reverse proxy. Le port de l'app
  (8080) reste bindé en local uniquement (`127.0.0.1:8080`, voir
  `docker-compose.prod.yml`) — il n'est jamais exposé directement.

### 3. Authentifier Docker sur GHCR si nécessaire

→ voir § Authentification GHCR ci-dessous (uniquement si le pull échoue).

### 4. Lancer l'installation

→ voir § Installation — une seule commande. À exécuter sur la VM cible, en
`root` ou un utilisateur membre du groupe `docker`.

### 5. Mettre en place le reverse proxy TLS

→ voir § Exposition HTTPS. Caddy (TLS automatique) ou Nginx + certbot selon
l'existant sur le reste du parc `*.yoops.org`.

### 6. Créer le premier compte admin

→ voir § Premier accès. À faire **immédiatement** après le smoke test : tant
qu'aucun utilisateur n'existe en base, `/api/setup/init-admin` est un
endpoint non authentifié.

### 7. (Optionnel) Configurer OIDC Keycloak

- Côté Keycloak (`security.yoops.org`, realm `yoops`) : créer un client
  `docflow` confidentiel, redirect URI
  `https://docflow.yoops.org/auth/oidc/callback`.
- Stocker le `client_secret` dans Harpocrate, jamais en clair — docflow ne
  référence que `${vault://...}` (voir `specs/17_M8_oidc.md`).
- Depuis le compte admin bootstrap : `PUT /admin/oidc` (ou l'IHM
  d'administration) avec issuer, `client_id`, `client_secret_ref`, puis
  activer.
- Vérifier après activation que le login local (break-glass) fonctionne
  toujours — c'est un invariant testé, pas une supposition.

### 8. (Optionnel) Renseigner HARPOCRATE_URL

Si des automates, wallets ou webhooks à secrets sont utilisés : décommenter
`HARPOCRATE_URL` dans `/data/.env`, puis redémarrer l'app :

```bash
docker compose -f /opt/docflow/docker-compose.prod.yml up -d --no-deps app
```

### 9. Configurer les sauvegardes

- Sauvegarde applicative : créer un job de sauvegarde + un remote point
  (FTP/FTPS/SFTP) depuis l'administration de l'app.
- Filet de sécurité indépendant du worker applicatif : installer le cron
  `pg_dump` décrit en § Sauvegarde.

### 10. Vérification finale

- `curl -sf https://docflow.yoops.org/health` → `200`.
- `GET /api/setup/status` → confirme qu'un utilisateur existe (wizard
  désactivé).
- Login admin via l'IHM.
- Si OIDC activé : tester un login fédéré **et** un login local (non-
  régression du break-glass, cf. § Décision 4 de `01_ARCHITECTURE.md`).

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

Préalable : merger `dev` → `main` (§ Procédure complète, étape 1) pour que
GHCR publie la nouvelle image `latest`. Puis, sur la VM :

```bash
bash /opt/docflow/prod-deploy.sh
```

Le script télécharge la dernière version de `docker-compose.prod.yml`, tire la nouvelle image et redémarre uniquement le conteneur app. Les migrations sont appliquées automatiquement.

---

## Déploiement dev (VM de test)

### Procédure complète — première installation

Checklist dans l'ordre, pour `test1` ou toute VM de dev équivalente.

#### 1. Pousser sur `dev`

Depuis le poste de dev, le code doit être disponible sur le remote avant tout
clone :

```bash
git push origin dev
```

#### 2. Se connecter sur la VM

```bash
ssh test1
```

#### 3. Générer une clé de déploiement dédiée (si pas encore fait)

```bash
ssh-keygen -t ed25519 -C "test1-docflow" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Donner la clé publique à enregistrer comme **Deploy Key GitHub** (lecture
seule) sur le dépôt `ag-flow/doc`.

#### 4. Cloner le repo

```bash
mkdir -p /opt/docflow
git clone git@github.com:ag-flow/doc.git /opt/docflow
cd /opt/docflow
git checkout dev
```

#### 5. Lancer le déploiement

```bash
sudo ./dev-deploy.sh dev
```

`/data/.env` et `/data/pg_password.txt` sont initialisés automatiquement
(copie de `deploy/.env.example` + secrets générés) — aucune saisie manuelle
requise. → voir le détail de ce que fait le script ci-dessous.

#### 6. Vérification finale

- Lire le récapitulatif affiché en fin de script : URL d'accès, état du
  compte admin, chemins `/data`, commande de suivi des logs.
- Créer le premier compte admin via le wizard si aucun compte n'existe
  (commande donnée dans le récapitulatif — même mécanisme qu'en prod, voir §
  Premier accès).
- `curl -sf http://<ip-vm>:8080/health` → `200`.

### Redéploiement (après chaque push sur `dev`)

```bash
ssh test1
cd /opt/docflow && sudo ./dev-deploy.sh dev
```

Idempotent, sans interruption de service au-delà du redémarrage du conteneur
`app` (le service `postgres` n'est pas touché s'il est déjà sain).

### Détail du script

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
4. **Smoke test** : `GET /health` (timeout 90 s), échec du script si KO, puis un
   récapitulatif : URL d'accès, état du compte admin (commande wizard si aucun
   compte), chemins `/data`, commande pour suivre les logs.

L'app est ensuite joignable en HTTP direct sur le LAN : `http://<ip-vm>:8080`
(stack de test sans reverse proxy — contrairement à la prod, qui reste bindée
sur `127.0.0.1` derrière le proxy TLS, cf. DEP-03).

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

### Prérequis vital — à faire AVANT d'avoir besoin de restaurer

Le dump ne contient **pas** la configuration de l'hôte. Ce qu'il faut comprendre
sur les trois secrets de `/data/.env` :

| Secret | Perte = quoi ? | Doit venir de l'ancienne instance ? |
|---|---|---|
| `ENCRYPTION_KEY` | **Irréversible** : certificats (clés privées git/SFTP), secrets locaux des remote points, headers webhooks, secrets d'automates — illisibles à jamais | **OUI, impérativement** |
| `JWT_SECRET` | Sessions ouvertes invalidées (les clés API survivent : hashées en base) | Souhaitable, pas critique |
| `DATABASE_URL` / `pg_password.txt` | Rien — doit simplement correspondre au Postgres **local** de l'instance qui restaure | **NON** (garder ceux du nouveau serveur) |

Deux façons d'avoir `ENCRYPTION_KEY`/`JWT_SECRET` sous la main le jour J :

1. **Automatique** : cocher « Déposer le matériel de restauration » sur le job
   dump — chaque archive `docflow_…​.dump` est alors accompagnée d'un
   `docflow_…​.key` (mêmes nom et date) contenant les trois valeurs.
2. **Manuelle** : copier `/data/.env` hors du serveur (coffre, vault, autre machine).

Le worker pousse les archives sur le remote point du job
(`docflow_<scope>_<date>_<heure>_<jobid>.dump`) ; la plus récente se repère par
son nom : `ls -1 docflow_*.dump | sort | tail -1` sur la machine de backup.

### La voie rapide — `deploy/restore.sh`

Le script automatise toute la mécanique des deux cas ci-dessous : report des
clés depuis un `.key` (auto-détecté à côté de l'archive), arrêt de l'app,
`pg_restore` strict, redémarrage (avec relecture de `/data/.env`) uniquement
si la restauration est complète, et rappel des vérifications. Confirmation
littérale `RESTORE` exigée (`--yes` pour les scripts).

```bash
# par-dessus l'instance (cas 1) :
sudo ./deploy/restore.sh /data/backups/docflow_all_…​.dump

# serveur neuf (cas 2), après l'installation de base — le .key posé à côté
# du .dump est détecté tout seul, sinon --key :
sudo ./deploy/restore.sh /data/backups/docflow_all_…​.dump --key /data/backups/docflow_all_…​.key
```

Les deux cas ci-dessous détaillent ce que le script fait — utiles pour
comprendre, déboguer, ou opérer à la main.

### Cas 1 — restauration par-dessus une instance existante

Le `/data/.env` en place est le bon (même instance) : rien à toucher côté
configuration. Si l'archive vient du worker, la rapatrier d'abord depuis la
machine de backup (nom `docflow_<scope>_<date>_<heure>_<jobid>.dump`) :

```bash
mkdir -p /data/backups
scp root@machine-backup:/chemin/docflow_all_…​.dump /data/backups/
```

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

Au démarrage, `apply` rejoue les migrations manquantes si le dump provient d'une
version plus ancienne que l'image — c'est le sens normal. **Ne jamais restaurer un
dump plus récent que l'image déployée** : mettre d'abord l'image à jour.

### Cas 2 — serveur tout neuf (reprise après sinistre)

> **Le point qui ne pardonne pas** : `ENCRYPTION_KEY` et `JWT_SECRET` doivent
> être en place dans `/data/.env` **avant le premier démarrage de l'app**.
> L'installeur, lui, en génère des neufs — d'où l'ordre ci-dessous. En
> revanche, mot de passe Postgres et `DATABASE_URL` restent ceux du nouveau
> serveur : le rôle Postgres est créé localement, le dump ne contient pas
> les mots de passe de rôles.

1. **Provisionner la machine et lancer l'installation** (§ Procédure complète,
   étapes 2-4). Laisser l'installeur générer `/data/.env` et démarrer la
   stack ; **ne pas créer le premier compte admin** (les comptes reviendront
   avec le dump) et **ne rien configurer d'autre**.
2. **Rapatrier depuis la machine de backup** l'archive la plus récente et son
   `.key` (ou le `/data/.env` sauvegardé manuellement) :
   ```bash
   mkdir -p /data/backups
   # la plus récente : ls -1 docflow_*.dump | sort | tail -1 côté backup
   scp root@machine-backup:/chemin/docflow_all_YYYYMMDD_HHMMSS_JOBID.dump /data/backups/
   scp root@machine-backup:/chemin/docflow_all_YYYYMMDD_HHMMSS_JOBID.key  /data/backups/
   chmod 600 /data/backups/*.key
   ```
3. **Reporter les clés de l'ancienne instance dans `/data/.env`** — c'est ce
   que fait `restore.sh --key` (avec sauvegarde `.bak` de l'ancien fichier) ;
   à la main :
   ```bash
   grep '^ENCRYPTION_KEY=\|^JWT_SECRET=' /data/backups/docflow_all_…​.key
   # → recopier ces deux lignes dans /data/.env (à la place des valeurs générées)
   ```
   **Ne PAS toucher** au `DATABASE_URL` du nouveau `/data/.env` ni à
   `/data/pg_password.txt` : ils correspondent au Postgres local. La ligne
   `DATABASE_URL` du `.key` ne sert qu'à documenter l'ancienne topologie.
   Sans le `.key` ni copie de l'ancien `.env` : la restauration reste
   possible, mais tous les secrets chiffrés sont perdus (recréer
   certificats — et re-déclarer leurs clés publiques côté GitHub /
   `authorized_keys` —, secrets de remote points, webhooks).
4. **Arrêter l'app et restaurer** (l'app doit être arrêtée : `--clean` droppe
   les objets sous ses pieds ; Postgres reste up) :
   ```bash
   cd /opt/docflow
   docker compose -f docker-compose.prod.yml stop app
   docker compose -f docker-compose.prod.yml exec -T postgres \
     pg_restore -U docflow -d docflow --clean --if-exists --no-owner --exit-on-error \
     < /data/backups/docflow_all_YYYYMMDD_HHMMSS_JOBID.dump
   echo "code de sortie pg_restore : $?"        # doit être 0
   ```
5. **Redémarrer l'app** — le `/data/.env` modifié n'est relu qu'à la
   re-création du conteneur, d'où `up -d --force-recreate` et non `start` :
   ```bash
   docker compose -f docker-compose.prod.yml up -d --force-recreate app
   ```
   Au boot, `apply` rejoue les migrations manquantes si le dump est plus
   ancien que l'image (jamais l'inverse : cf. Cas 1).
6. **Vérifier, dans cet ordre** :
   - connexion avec un compte d'avant le sinistre (auth = données du dump) ;
   - workspaces/documents présents ;
   - **Tester** sur chaque remote point → ✓ (c'est LE test de
     l'`ENCRYPTION_KEY` : il déchiffre la clé privée du certificat) ;
   - un run de backup manuel de bout en bout.
7. **Reconfigurer ce qui vit hors base et hors dump** : reverse proxy TLS,
   DNS, et remettre en place la sauvegarde du nouveau `/data/.env` (ou
   recocher l'option `.key` sur le job dump restauré).

### Et le miroir git ?

Le backup `git_sync` est un **export complet et lisible du contenu documentaire** :

```
<workspace>/                      ← marqueur .docflow-workspace
  <bloc>/<sous-bloc>/             ← un répertoire par bloc (hiérarchie réelle)
    _block.yaml                   ← slug/label du bloc + template du type racine
                                    (sous-types, propriétés, contraintes, valeurs autorisées)
    <doc>.md                      ← contenu markdown du document
    <doc>.json                    ← titre, type, propriétés
    <doc>/<enfant>.md …           ← descendance du document
```

Chaque commit est un état daté du contenu. Il permet de reconstruire un
workspace : recréer les types depuis les `_block.yaml` (format aligné sur les
templates importables), les blocs d'après l'arborescence, puis recoller les
documents (`.md` + propriétés du `.json`).

Il ne contient en revanche **ni les comptes, ni les certificats/secrets, ni
l'historique des versions** : la restauration complète d'une instance passe
toujours par le dump Postgres (§ ci-dessus).

#### Restaurer depuis le miroir git

**Depuis l'IHM (voie normale)** : sur l'instance à réalimenter, recréer un
certificat SSH (Générer, clé publique à déclarer en deploy key du repo de
sauvegarde — lecture suffit) et un remote point git, puis onglet
**Sauvegarde → Restauration depuis le miroir git** : choisir le point, le
sous-répertoire éventuel (le « base path » du job d'origine), et Restaurer.
Le bilan (créés/réalignés/erreurs) s'affiche à la fin.

**En ligne de commande (équivalent)** : la CLI recrée workspaces, types (via
l'importeur de templates), blocs et documents depuis un clone du repo de
sauvegarde.
**Additive et idempotente** : elle crée ce qui manque, réaligne
titre/contenu/propriétés des documents existants, et ne supprime jamais rien
— utilisable aussi bien sur une instance vide (serveur neuf, sans dump) que
par-dessus une instance vivante.

```bash
# 1. Cloner le repo de sauvegarde sur la VM
git clone git@github.com:org/backup-repo.git /tmp/restore-docflow

# 2. Copier le clone dans le conteneur app et lancer la restauration
docker compose -f /opt/docflow/docker-compose.prod.yml cp /tmp/restore-docflow app:/tmp/restore
docker compose -f /opt/docflow/docker-compose.prod.yml exec app \
  python -m docflow.backup.restore_git_cli /tmp/restore            # tout
#                            … restore_git_cli /tmp/restore --workspace doc   # un seul workspace
```

La commande affiche le bilan (workspaces/blocs/documents créés, documents
réalignés) et sort en erreur si un élément n'a pas pu être restauré (conflit
de types, propriété disparue…) — les autres éléments sont restaurés quand même.
