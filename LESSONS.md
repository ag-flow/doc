# LESSONS — docflow

## [frontend] SecretInput : toutes les clés à sécuriser utilisent le composant SecretInput
Chaque champ destiné à stocker un secret (client_secret OIDC, API key, token, password…) doit utiliser le composant `SecretInput` (`components/SecretInput.tsx`) plutôt qu'un `<Input type="password">` brut. Ce composant expose un select "En local | wallet-A | …" + un input : si un wallet est choisi, la valeur produite est `${vault://walletname:/chemin}` ; en local, la valeur brute est stockée chiffrée dans la DB.

## [templates] No-op vérification : calculer le diff AVANT le check no_op
Dans `templates/importer.py`, le no_op était évalué avant le calcul du diff, bloquant le ré-import d'un template quand tous les types du workspace avaient été supprimés. Règle : calculer le diff en premier, puis no_op seulement si `current_version == template.version AND diff vide`.

## [frontend] Commits package.json + package-lock.json après npm install
Après `npm install` en dev local, toujours committer `package.json` ET `package-lock.json` avant de livrer. `docker compose build` utilise `npm ci` qui échoue si le lock file ne correspond pas.

## [tools] Lire le fichier avant Edit
Le tool `Edit` exige que le fichier ait été lu dans la même session (sinon "File has not been read yet"). Après une compaction de contexte, toujours re-lire le fichier cible avant de tenter une édition.
