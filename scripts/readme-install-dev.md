# Installation d'une VM de test docflow (Proxmox)

Procédure complète pour provisionner une **nouvelle machine de test** depuis
zéro sur Proxmox, l'enrôler dans le portail devpod, jusqu'au premier
déploiement de docflow dessus. À suivre dans l'ordre.

> Pour le redéploiement après un push sur `dev` (machine déjà existante), voir
> `deploy/DEPLOY.md` § Déploiement dev — pas besoin de repasser par ce
> document.

## 1. Se connecter au serveur Proxmox

```bash
ssh pve
```

(`pve` : alias SSH configuré localement. Second nœud du cluster disponible :
`pve2`, si besoin de répartir la charge.)

## 2. Créer le container LXC

```bash
./01-create-lxc.sh <CTID> <hostname>
# ex : ./01-create-lxc.sh 304 docflow-test
```

Script présent sur l'hôte Proxmox (`/root/01-create-lxc.sh`), pas dans ce
dépôt. Idempotent : si `<CTID>` n'existe pas encore, crée le container
(Ubuntu, Docker installé via `01-install-docker.sh`) ; s'il existe déjà,
reconfigure Docker dessus. **À la fin de son exécution, il affiche les
informations de connexion à conserver** (adresse IP, clé SSH générée sous
`/root/.ssh/lxc-keys` sur l'hôte Proxmox) — à noter immédiatement.

`pct list` sur `pve` donne l'inventaire des CTID déjà utilisés, pour choisir
un identifiant libre.

## 3. Se connecter au container nouvellement créé

```bash
ssh <utilisateur>@<adresse>   # informations données par 01-create-lxc.sh à l'étape 2
```

## 4. Enrôler le nœud dans le portail devpod

```bash
curl -sSL https://raw.githubusercontent.com/ag-flow/doc/main/scripts/install-node.sh | bash -s -- \
  --portal <URL du portail devpod> --token <token d'enrôlement> \
  --node-name docflow-test --address <adresse du container, étape 2>
```

Script vendored dans ce dépôt (`scripts/install-node.sh`, copié depuis
[`devpod-ui`](https://github.com/gaelgael5/devpod-ui/blob/main/scripts/install-node.sh)).
Installe Docker si absent (idempotent), génère un certificat mTLS pour le
daemon Docker, l'enrôle auprès du portail (`${PORTAL}/admin/nodes/enroll`),
configure le pare-feu (port 2376 restreint à l'IP du portail) et prépare le
builder buildx + l'image `mcp-runner`.

- `--token` : token d'enrôlement à obtenir depuis le portail devpod
  (administration → nœuds).
- `--node-name` : `^[a-z0-9][a-z0-9-]{0,30}[a-z0-9]$` (ex. `docflow-test`).
- `--address` : IP ou hostname du container (étape 2/3).

## 5. Générer un certificat SSH dédié + l'enregistrer sur GitHub

Nécessaire uniquement si le dépôt `ag-flow/doc` est privé (accès en lecture
pour le clone).

```bash
ssh-keygen -t ed25519 -C "<nom-noeud>-docflow" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Copier la clé publique affichée et l'enregistrer comme **Deploy Key**
(lecture seule) sur GitHub : dépôt `ag-flow/doc` → *Settings* → *Deploy
keys* → *Add deploy key*.

## 6. Cloner le dépôt dans `/opt`

```bash
mkdir -p /opt/docflow
git clone git@github.com:ag-flow/doc.git /opt/docflow
cd /opt/docflow
git checkout dev
```

## 7. Lancer le déploiement

```bash
sudo ./dev-deploy.sh dev
```

Idempotent : initialise `/data/.env` et `/data/pg_password.txt` (secrets
générés automatiquement), build l'image, démarre la stack (app + postgres),
applique les migrations, smoke-test `GET /health`, puis affiche un
récapitulatif (URL d'accès, état du compte admin, chemins `/data`, commande
de suivi des logs).

## Voir aussi

- `deploy/DEPLOY.md` § Déploiement dev (VM de test) — détail de ce que fait
  `dev-deploy.sh` en interne, et procédure de **redéploiement** (2
  commandes) après chaque push sur `dev`.
- `CLAUDE.md` § Déploiement sur la VM de test — machine de référence
  courante.
