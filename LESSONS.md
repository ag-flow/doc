# LESSONS — docflow

## [frontend] SecretInput : toutes les clés à sécuriser utilisent le composant SecretInput
Chaque champ destiné à stocker un secret (client_secret OIDC, API key, token, password…) doit utiliser le composant `SecretInput` (`components/SecretInput.tsx`) plutôt qu'un `<Input type="password">` brut. Ce composant expose un select "En local | wallet-A | …" + un input : si un wallet est choisi, la valeur produite est `${vault://walletname:/chemin}` ; en local, la valeur brute est stockée chiffrée dans la DB.

## [templates] No-op vérification : calculer le diff AVANT le check no_op
Dans `templates/importer.py`, le no_op était évalué avant le calcul du diff, bloquant le ré-import d'un template quand tous les types du workspace avaient été supprimés. Règle : calculer le diff en premier, puis no_op seulement si `current_version == template.version AND diff vide`.

## [frontend] Commits package.json + package-lock.json après npm install
Après `npm install` en dev local, toujours committer `package.json` ET `package-lock.json` avant de livrer. `docker compose build` utilise `npm ci` qui échoue si le lock file ne correspond pas.

## [tools] Lire le fichier avant Edit
Le tool `Edit` exige que le fichier ait été lu dans la même session (sinon "File has not been read yet"). Après une compaction de contexte, toujours re-lire le fichier cible avant de tenter une édition.

## [deploy] Script dev-deploy.sh : bit +x dans git obligatoire
Le script `scripts/dev-deploy.sh` doit avoir le bit exécutable dans git (`git update-index --chmod=+x`). Sans ça, `./scripts/dev-deploy.sh` échoue avec "Permission denied" sur la VM et il faut passer par `bash scripts/dev-deploy.sh`. Toujours vérifier le bit +x après création d'un nouveau script shell.

## [deploy] Redéploiement VM nécessaire après push
Les changements frontend/backend ne sont visibles à l'écran qu'après un redéploiement sur la VM de test : `ssh test1 "cd /opt/docflow && ./scripts/dev-deploy.sh dev"`. Un `git push` seul ne suffit pas.

## [harpocrate] SDK Python synchrone — utiliser asyncio.to_thread
Le SDK Python Harpocrate (`harpocrate.VaultClient`) est **synchrone** (utilise `httpx.request` sync). Pour l'appeler depuis le code async FastAPI, l'encapsuler dans `asyncio.to_thread(_fetch)`. Ne jamais appeler le SDK directement dans un handler async.

## [harpocrate] Format de référence et résolution
- Format : `${vault://wallet_name:/chemin/vers/secret}`
- `wallet_name` = nom dans la table `vault_wallet` (notre DB), pas directement dans Harpocrate
- Résolution : chercher l'api_key du wallet dans la DB → `VaultClient(token=api_key, base_url=harpocrate_url).secrets.get("/chemin/vers/secret")`
- Le SDK gère lui-même le déchiffrement E2E côté client (AES-GCM, wallet_key cachée)
- Dépendance : `harpocrate>=0.6.0` via `[tool.uv.sources]` → wheel sur `vault.yoops.org`

## [fastapi] Routes statiques avant routes paramétriques dans le même préfixe
FastAPI évalue les routes dans l'ordre d'enregistrement. Si `GET /documents/{doc_id: UUID}` est enregistré avant `GET /documents/search`, FastAPI capture "search" avec le paramètre `{doc_id}`, échoue la validation UUID, et retourne 422 sans fallback. Règle : toujours placer les routes statiques (chemins littéraux) **avant** les routes paramétriques (`{param}`) dans le même router, ou les déplacer dans le même router si elles sont dans des routers différents inclus dans un ordre défavorable.

## [harpocrate] OpenAPI disponible sans auth
La spec OpenAPI de Harpocrate (endpoints API key) est accessible sans authentification : `GET https://vault.yoops.org/v1/openapi-api-key.json`. Utile pour vérifier les routes et schémas disponibles.

## [migration] Numérotation des migrations : vérifier avant d'écrire
La numérotation des migrations peut diverger des specs si une migration a été ajoutée entre temps (ex : wizard → 0021). Toujours vérifier les fichiers existants dans `backend/migrations/` avant d'écrire une nouvelle migration pour éviter les collisions.

## [asyncpg] AuthUser : le champ id, pas user_id
Le modèle `AuthUser` (schemas/auth.py) expose le champ `id: uuid.UUID`, pas `user_id`. Dans les routers, accéder à `current.id` pour l'identifiant de l'utilisateur connecté.


## [filter_engine] Renumérotation des placeholders $n : fragile
La renumérotation manuelle des `$i` → `$i+offset` (dans views/service.py) est fragile si les placeholders ont plus de 9 digits (`$1` → `$11` peut matcher `$10`). Préférer des systèmes qui construisent la liste de params en séquence sans renumérotation.
