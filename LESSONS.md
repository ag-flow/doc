# LESSONS — docflow

## [tests] Pytest conteneurisé : monter tout le repo, pas seulement backend/
Les tests templates lisent `templates/*.yaml` à la racine du repo et GitPython exige le binaire `git`. Monter `/opt/docflow` entier (workdir `backend/`) et installer git dans le conteneur, sinon 14 échecs FileNotFoundError trompeurs.

## [frontend] SecretInput : toutes les clés à sécuriser utilisent le composant SecretInput
Chaque champ destiné à stocker un secret (client_secret OIDC, API key, token, password…) doit utiliser le composant `SecretInput` (`components/SecretInput.tsx`) plutôt qu'un `<Input type="password">` brut. Ce composant expose un select "En local | wallet-A | …" + un input : si un wallet est choisi, la valeur produite est `${vault://walletname:/chemin}` ; en local, la valeur brute est stockée chiffrée dans la DB.

## [templates] No-op vérification : calculer le diff AVANT le check no_op
Dans `templates/importer.py`, le no_op était évalué avant le calcul du diff, bloquant le ré-import d'un template quand tous les types du workspace avaient été supprimés. Règle : calculer le diff en premier, puis no_op seulement si `current_version == template.version AND diff vide (adds/soft_updates)`.

## [templates] La galerie de templates existe déjà — vérifier le code avant de bâtir du neuf
`templates/gallery.py` + table `gallery_source` implémentent déjà un pull distant (`toc.txt` + `<slug>.yaml` sur une URL de base HTTP). "Sortir les templates dans un repo dédié" = juste servir `templates/` en raw HTTP + enregistrer l'URL comme source, aucun code à écrire.

## [frontend] Commits package.json + package-lock.json après npm install
Après `npm install` en dev local, toujours committer `package.json` ET `package-lock.json` avant de livrer. `docker compose build` utilise `npm ci` qui échoue si le lock file ne correspond pas.

## [tools] Lire le fichier avant Edit
Le tool `Edit` exige que le fichier ait été lu dans la même session (sinon "File has not been read yet"). Après une compaction de contexte, toujours re-lire le fichier cible avant de tenter une édition.

## [deploy] dev-deploy.sh doit être +x en git ; redéploiement VM obligatoire après push
Un nouveau script shell doit avoir le bit exécutable committé (`git update-index --chmod=+x`), sinon "Permission denied" sur la VM. Par ailleurs un `git push` seul ne rend rien visible : il faut `ssh test1 "cd /opt/docflow && ./scripts/dev-deploy.sh dev"` pour redéployer.

## [deploy] Pas d'accès GitHub direct depuis ce sandbox — relayer via test1
Ni SSH ni le credential-helper HTTPS du devpod n'autorisent un push GitHub depuis ce sandbox. Relayer : `git push test1:/opt/docflow dev:dev` (repo local sur la VM, `receive.denyCurrentBranch=updateInstead`) puis `ssh test1 'cd /opt/docflow && git push origin dev'` (test1 a sa propre clé enregistrée). Nécessite aussi `git config --local user.name/user.email` (pas global) alignés sur l'auteur existant du repo.

## [testing] Pas de Docker/Postgres dans ce sandbox — Postgres éphémère sur test1 + tunnel SSH
Pour les tests DB : `docker run -p 127.0.0.1:PORT:5432 postgres:16-alpine ...` sur test1, puis `ssh -f -N -L PORT:127.0.0.1:PORT test1`, puis `DATABASE_URL=... uv run pytest` en local. Détruire le conteneur après usage. Pour les tests qui bootent l'app complète (TestClient/lifespan), `/data` doit exister en écriture (`sudo mkdir /data`) — `backup/worker.py` y écrit sans condition ; en vrai déploiement ça tourne en root donc ce n'est pas un bug, juste une limite du sandbox.

## [testing] Toujours lancer la suite ENTIÈRE avant de chiffrer un scope de correction
Un sous-ensemble de fichiers testés peut masquer l'essentiel : 12 échecs identifiés sur un sous-ensemble contre ~130 réels sur la suite complète (`uv run pytest` sans filtre). Ne jamais conclure sur le scope d'un correctif sans avoir vu le résumé final complet (`tail` peut tronquer le haut du résumé si beaucoup d'échecs).

## [migrations] Un test qui échoue après une migration n'est pas forcément un bug à corriger dans le code
Plusieurs migrations (0010, 0011, 0027) ont délibérément inversé RESTRICT→CASCADE ou renommé table/colonne (`admin_user`→`app_user`, `is_superadmin`→`is_admin`), documenté dans le commentaire SQL de la migration. Toujours lire ce commentaire avant de "corriger" — le bon geste est souvent de réécrire le test pour vérifier le nouveau comportement voulu, jamais de réintroduire l'ancien comportement en code.

## [security] Jamais un secret fraîchement généré dans la sortie d'une commande, même "pour vérifier"
Le classifier de permissions bloque à raison tout `echo`/`cat` d'un mot de passe généré. Écrire directement dans le fichier cible (heredoc, `>`) sans jamais faire transiter la valeur par un terminal capturé.

## [harpocrate] SDK Python synchrone — utiliser asyncio.to_thread
`harpocrate.VaultClient` est **synchrone**. Depuis FastAPI async, l'encapsuler dans `asyncio.to_thread(_fetch)`, jamais d'appel direct dans un handler async. Format de référence : `${vault://wallet_name:/chemin}` — `wallet_name` = nom dans notre table `vault_wallet`, résolu via `VaultClient(token=api_key, base_url=harpocrate_url).secrets.get(...)`. Dépendance `harpocrate>=0.6.0` via `[tool.uv.sources]`.

## [fastapi] Routes statiques avant routes paramétriques dans le même préfixe
`GET /documents/{doc_id: UUID}` enregistré avant `GET /documents/search` capture "search" comme UUID → 422. Toujours déclarer les chemins littéraux avant les `{param}` dans le même router.

## [migration] Vérifier la numérotation existante avant d'écrire une nouvelle migration
Peut diverger des specs si une migration a été ajoutée entretemps (ex. wizard → 0021). Toujours lister `backend/migrations/` avant d'assigner un numéro.

## [asyncpg] AuthUser : champs actuels = id, is_admin, validated (pas user_id / is_superadmin)
`schemas/auth.py::AuthUser` a été fait évoluer (migration 0027) : `is_superadmin`→`is_admin`, ajout de `validated` (un compte OIDC auto-provisionné est non validé → 403 PendingValidation tant qu'un admin ne l'a pas validé). Le bootstrap admin par variable d'env est supprimé (`auth/seed.py`), remplacé par le setup wizard (`POST /api/setup/init-admin`) ; `Settings` n'a plus `admin_email`/`admin_password`.

## [filter_engine] Renumérotation des placeholders $n : fragile
La renumérotation manuelle des `$i` → `$i+offset` (views/service.py) est fragile si les placeholders dépassent 9 (`$1`→`$11` peut matcher `$10`). Préférer construire la liste de params en séquence sans renumérotation.
