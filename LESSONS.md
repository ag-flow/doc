# LESSONS — docflow

## [env] Capacités du sandbox : vérifier, ne pas présumer
L'accès GitHub, Docker/Postgres local et SSH test1 varient selon le sandbox. Vérifier au début (git push --dry-run, psql) au lieu de rejouer un contournement d'une session passée. Si push direct impossible : relayer via la VM (`git push test1:/opt/docflow dev:dev` puis push depuis la VM). Si pas de Postgres local : conteneur éphémère sur la VM + tunnel SSH ; les tests full-app exigent `/data` inscriptible.

## [frontend] SecretInput : toutes les clés à sécuriser utilisent le composant SecretInput
Chaque champ destiné à stocker un secret (client_secret OIDC, API key, token, password…) doit utiliser `components/SecretInput.tsx`, jamais un `<Input type="password">` brut. Wallet choisi → valeur `${vault://walletname:/chemin}` ; en local → valeur chiffrée en DB.

## [frontend] Typecheck local : `npx tsc -b`, jamais `tsc --noEmit`
Le tsconfig racine est une « solution » (references only) : `tsc --noEmit` ne vérifie RIEN et sort vert. Le build Docker fait `tsc -b` (tests inclus) — toute propriété requise ajoutée à une interface doit être répercutée dans les fixtures de test.

## [frontend] Onglets à montage conditionnel : jamais de valeur de submit dans un ref d'enfant
Un champ dont la valeur vit dans un composant monté conditionnellement (onglet, accordéon) est perdu au démontage : `ref.current` devient null et un submit depuis un autre onglet envoie null → effacement silencieux en base (bug body_template des automates). Toute valeur soumise vit dans le state du formulaire parent ; l'enfant (CodeMirror…) n'est qu'une vue avec onChange.

## [frontend] Committer package.json ET package-lock.json après npm install
`docker compose build` utilise `npm ci`, qui échoue si le lock ne correspond pas.

## [templates] Lire le code existant avant de bâtir du neuf ; no_op après le diff
La galerie distante existe (`templates/gallery.py` + `gallery_source`) : « externaliser les templates » = servir le dossier en raw HTTP et enregistrer la source. Dans `importer.py`, calculer le diff AVANT le check no_op, sinon le ré-import est bloqué quand les types du workspace ont été supprimés.

## [tests] Suite ENTIÈRE avant de chiffrer un scope ; conteneur pytest = repo entier
Un sous-ensemble masque l'essentiel (12 échecs vus contre ~130 réels). En conteneur, monter tout le repo (les tests templates lisent `templates/*.yaml` à la racine) et installer `git` (GitPython).

## [migrations] Numérotation et intentions : lire avant d'écrire
Lister `backend/migrations/` avant d'assigner un numéro (les specs peuvent être en retard). Un test qui casse après migration n'est pas forcément un bug : plusieurs migrations (0010, 0011, 0027) changent délibérément le comportement (RESTRICT→CASCADE, `admin_user`→`app_user`, `is_superadmin`→`is_admin`) — lire le commentaire SQL, adapter le test, ne jamais réintroduire l'ancien comportement.

## [security] Jamais un secret dans la sortie d'une commande, même « pour vérifier »
Écrire directement dans le fichier cible (heredoc, `>`) sans faire transiter la valeur par un terminal capturé.

## [harpocrate] SDK Python synchrone — utiliser asyncio.to_thread
`harpocrate.VaultClient` est synchrone : l'encapsuler dans `asyncio.to_thread`, jamais d'appel direct dans un handler async. Référence : `${vault://wallet_name:/chemin}`, résolue via `VaultClient(...).secrets.get(...)`.

## [fastapi] Routes statiques avant routes paramétriques dans le même préfixe
`GET /documents/{doc_id: UUID}` déclaré avant `/documents/search` capture « search » comme UUID → 422.

## [auth] AuthUser : champs actuels = id, is_admin, validated
Migration 0027 : `is_superadmin`→`is_admin`, ajout `validated` (compte OIDC auto-provisionné → 403 PendingValidation tant que non validé). Bootstrap admin par env supprimé, remplacé par `POST /api/setup/init-admin`.

## [filter_engine] Renumérotation des placeholders $n : fragile
`$i`→`$i+offset` casse au-delà de 9 (`$1`→`$11` matche `$10`). Construire la liste de params en séquence, sans renumérotation.

## [automations] Le contenu document vit dans document_version, pas document
Contenu courant = `document_version.content` à `version_number = document.version` (JOIN). `SELECT content FROM document` n'existe pas.

## [git] git add multi-chemins : un pathspec invalide annule TOUT le add
Un `git commit` chaîné commit alors le staging PARTIEL précédent (commit cassé poussé une fois). Utiliser `git add -A` ou vérifier `git status --short` avant commit.

## [tools] Lire le fichier avant Edit
Après une compaction de contexte, re-lire le fichier cible avant toute édition (« File has not been read yet »).

## [deploy] Bit exécutable committé + redéploiement obligatoire
Nouveau script shell : `git update-index --chmod=+x`. Un push seul ne rend rien visible : redéployer sur la VM (`sudo ./dev-deploy.sh dev`).
