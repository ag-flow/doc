# LESSONS — docflow

## [env] Capacités du sandbox : vérifier, ne pas présumer
GitHub, Docker/Postgres local et SSH test1 varient selon le sandbox. Vérifier au début (git push --dry-run, psql) au lieu de rejouer un contournement passé. Pas de Postgres local : conteneur éphémère sur la VM + tunnel SSH ; tests full-app exigent `/data` inscriptible.

## [frontend] SecretInput : toutes les clés à sécuriser passent par lui
Jamais un `<Input type="password">` brut pour un secret. Wallet → `${vault://walletname:/chemin}` ; local → chiffré en DB.

## [frontend] Typecheck : `npx tsc -b` depuis frontend/, jamais `--noEmit` ni depuis la racine
Le tsconfig racine est une « solution » : `--noEmit` ne vérifie rien. À la racine du repo, vitest tourne sans jsdom (« document is not defined ») et npx résout un faux paquet `tsc`. Toute propriété requise ajoutée à une interface se répercute dans les fixtures de test.

## [frontend] Onglets à montage conditionnel : jamais de valeur de submit dans un ref d'enfant
Un champ monté conditionnellement perd sa valeur au démontage → submit null → effacement silencieux (bug body_template). Toute valeur soumise vit dans le state du parent.

## [frontend] Committer package.json ET package-lock.json après npm install
`docker compose build` fait `npm ci`, qui échoue si le lock diverge.

## [css] Le CSS non-layered bat TOUJOURS les utilitaires Tailwind (@layer)
`.dialog{width:min(440px,100%)}`, `.input{width:100%}` : les `w-*`/`!max-w-*` posés sur l'élément perdent. Largeur voulue → la poser sur un CONTENEUR, ou écrire la règle globale en `width:100%` + `max-width` surchargeable.

## [react] Tableau par défaut (`data ?? []`) + setState dans useEffect = boucle sous act()
L'identité change à chaque rendu ; un setState inconditionnel gèle vitest en boucle synchrone. Garder `if (data.length === 0) return`.

## [templates] Lire le code existant avant de bâtir du neuf ; no_op après le diff
La galerie distante existe (`templates/gallery.py`). Dans `importer.py`, calculer le diff AVANT le check no_op, sinon ré-import bloqué après suppression des types.

## [tests] Suite ENTIÈRE avant de chiffrer un scope ; conteneur pytest = repo entier
Un sous-ensemble masque l'essentiel. Monter tout le repo (tests templates lisent `templates/*.yaml`) et installer `git`.

## [migrations] Numérotation et intentions : lire avant d'écrire
Lister `backend/migrations/` avant d'assigner un numéro. Un test cassé après migration reflète parfois un changement voulu (0010/0011/0027) — lire le commentaire SQL, adapter le test.

## [security] Jamais un secret dans la sortie d'une commande, même « pour vérifier »
Écrire directement dans le fichier cible (heredoc, `>`), sans transit par un terminal capturé.

## [harpocrate] SDK Python synchrone — asyncio.to_thread
Jamais d'appel direct dans un handler async. Référence `${vault://wallet:/chemin}` via `VaultClient(...).secrets.get(...)`.

## [fastapi] Routes statiques avant routes paramétriques dans le même préfixe
`/documents/{doc_id: UUID}` déclaré avant `/documents/search` capture « search » → 422.

## [auth] AuthUser : id, is_admin, validated (migration 0027)
Compte OIDC auto-provisionné → 403 PendingValidation tant que non validé. Bootstrap via `POST /api/setup/init-admin`.

## [filter_engine] Renumérotation des placeholders $n : fragile
`$1`→`$11` matche `$10`. Construire la liste de params en séquence, sans renumérotation.

## [automations] Le contenu document vit dans document_version, pas document
Contenu courant = `document_version.content` à `version_number = document.version` (JOIN).

## [git] git add multi-chemins : un pathspec invalide annule TOUT le add
Le commit chaîné embarque alors le staging partiel précédent. `git add -A` ou `git status --short` avant commit.

## [tools] Lire le fichier avant Edit
Après compaction de contexte, re-lire la cible avant toute édition.

## [deploy] Bit exécutable committé + redéploiement obligatoire
Script shell : `git update-index --chmod=+x`. Un push seul ne montre rien : `sudo ./dev-deploy.sh dev` sur la VM.
