# Installation d'une VM de test docflow (Proxmox)

Procédure complète pour provisionner une **nouvelle VM de test** depuis zéro
sur Proxmox, jusqu'au premier déploiement de docflow dessus. À suivre dans
l'ordre.

> Pour le redéploiement après un push sur `dev` (VM déjà existante), voir
> `deploy/DEPLOY.md` § Déploiement dev — pas besoin de repasser par ce
> document.

## 1. Se connecter au serveur Proxmox

```bash
ssh pve
```

(`pve` = 192.168.10.41. Second nœud du cluster disponible : `pve2` =
192.168.10.152, si besoin de répartir la charge.)

## 2. Lancer `create-node.sh` — une seule commande

```bash
wget -qO- https://raw.githubusercontent.com/ag-flow/doc/main/scripts/create-node.sh | bash
```

Ce script crée la machine virtuelle. **À la fin de son exécution, il affiche
les informations de connexion à conserver** (adresse IP, identifiants…) — à
noter immédiatement, elles ne sont pas ré-affichées ensuite.

> ⚠️ `scripts/create-node.sh` n'existe pas encore dans ce dépôt à ce jour
> (vérifié sur `main` et `dev`) — la commande ci-dessus échouera tant qu'il
> n'aura pas été ajouté à `scripts/` sur `main`.

## 3. Se connecter à la VM nouvellement créée

```bash
ssh <utilisateur>@<ip-vm>   # informations données par create-node.sh à l'étape 2
```

## 4. Générer un certificat SSH dédié + l'enregistrer sur GitHub

Nécessaire uniquement si le dépôt `ag-flow/doc` est privé (accès en lecture
pour le clone).

```bash
ssh-keygen -t ed25519 -C "<nom-vm>-docflow" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Copier la clé publique affichée et l'enregistrer comme **Deploy Key**
(lecture seule) sur GitHub : dépôt `ag-flow/doc` → *Settings* → *Deploy
keys* → *Add deploy key*.

## 5. Cloner le dépôt dans `/opt`

```bash
mkdir -p /opt/docflow
git clone git@github.com:ag-flow/doc.git /opt/docflow
cd /opt/docflow
git checkout dev
```

## 6. Lancer le déploiement

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
