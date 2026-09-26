# LESSONS — docflow

Format : `- [module] erreur observée → bonne pratique`. Une leçon par ligne, 50 lignes au plus — au-delà, consolider.

- [env] Les capacités du sandbox (GitHub, Docker/Postgres local, SSH test1) varient → les vérifier au début (`git push --dry-run`, `psql`) au lieu de rejouer un contournement passé. Sans Postgres local : conteneur éphémère sur la VM + tunnel SSH ; les tests full-app exigent `/data` inscriptible.
- [livraison] Un commit non poussé n'existe pour personne : l'utilisateur redéploie du code inchangé et voit « aucune différence » → pousser sur `dev` systématiquement (commit ET push, sans demander), jamais sur `main`, et si un push est refusé le dire en PREMIÈRE LIGNE, pas en bas d'un récapitulatif.
- [deploy] Un push seul ne montre rien → `sudo ./dev-deploy.sh dev` sur la VM. Bit exécutable d'un script : `git update-index --chmod=+x`.
- [git] Un pathspec invalide annule TOUT le `git add`, et le commit chaîné embarque le staging partiel précédent → `git add -A`, ou `git status --short` avant commit.
- [tools] Après compaction de contexte, l'état d'un fichier n'est plus fiable → le relire avant toute édition.
- [tests] Un sous-ensemble de tests masque l'essentiel → jouer la suite ENTIÈRE avant de chiffrer un scope. Le conteneur pytest monte le repo entier (les tests de templates lisent `templates/*.yaml`) et a besoin de `git`.
- [tests] Un mock qui ment cache un bug : `listDocuments` rend des TÊTES (`content` toujours `null`) → le mock doit refléter l'API réelle, sinon il masque un diagramme sans titres, sans champs et sans relations.
- [tests] Ce qui n'est pas observable au rendu sous jsdom (géométrie, choix d'un côté d'ancrage) → le tester sur la fonction pure qui le décide, sinon l'appel peut disparaître sans qu'aucun test ne tombe.
- [css] Le CSS non-layered bat TOUJOURS les utilitaires Tailwind (`@layer`) → une largeur voulue se pose sur un CONTENEUR, ou la règle globale s'écrit `width:100%` + `max-width` surchargeable.
- [css] À spécificité égale, la dernière règle du fichier gagne : `.doc-sheet table` neutralisait `.doc-sheet-wide table` → une variante qui doit gagner se décide par la SPÉCIFICITÉ (`.doc-sheet.doc-sheet-wide table`), jamais par l'ordre des lignes, et se verrouille par un test sur la feuille produite.
- [css] Tailwind v4 a retiré `cursor: pointer` des boutons de son preflight → un élément cliquable doit le déclarer ; le poser une fois en base d'élément plutôt que classe par classe.
- [frontend] Jamais un `<Input type="password">` brut pour un secret → passer par `SecretInput`. Wallet = `${vault://walletname:/chemin}` ; local = chiffré en DB.
- [frontend] `npx tsc -b` depuis `frontend/`, jamais `--noEmit` depuis la racine : le tsconfig racine est une « solution » et ne vérifie rien ; à la racine, vitest tourne sans jsdom et npx résout un faux paquet `tsc`.
- [frontend] Un champ monté conditionnellement perd sa valeur au démontage → submit `null` → effacement silencieux (bug `body_template`) : toute valeur soumise vit dans le state du parent, jamais dans un ref d'enfant.
- [frontend] Committer `package.json` ET `package-lock.json` : `docker compose build` fait `npm ci`, qui échoue si le lock diverge.
- [frontend] Un `<select>` reconstruit depuis une liste d'options perd une valeur absente de cette liste au premier rendu → conserver la valeur inconnue et la signaler, sinon afficher le formulaire réécrit la donnée.
- [react] `data ?? []` + setState inconditionnel dans un `useEffect` = boucle synchrone sous `act()` (l'identité du tableau change à chaque rendu) → garder `if (data.length === 0) return`.
- [react] Figer un document dérivé dans un state le fige avec les données connues au premier changement émis par le moteur de rendu (avant chargement) → ne garder en state que ce que l'utilisateur modifie ; la sémantique vient toujours de la requête.
- [migrations] Lister `backend/migrations/` avant d'assigner un numéro. Un test cassé après migration reflète parfois un changement voulu (0010/0011/0027) → lire le commentaire SQL, adapter le test.
- [security] Jamais un secret dans la sortie d'une commande, même « pour vérifier » → écrire directement dans le fichier cible (heredoc, `>`), sans transit par un terminal capturé.
- [harpocrate] SDK Python synchrone → `asyncio.to_thread`, jamais d'appel direct dans un handler async. Référence `${vault://wallet:/chemin}` via `VaultClient(...).secrets.get(...)`.
- [fastapi] Routes statiques AVANT routes paramétriques dans un même préfixe : `/documents/{doc_id:UUID}` déclaré avant `/documents/search` capture « search » → 422.
- [auth] `AuthUser` : id, is_admin, validated (migration 0027). Compte OIDC auto-provisionné → 403 PendingValidation tant que non validé ; bootstrap via `POST /api/setup/init-admin`.
- [filter_engine] Renumérotation des placeholders `$n` fragile (`$1`→`$11` matche `$10`) → construire la liste de params en séquence, sans renumérotation.
- [artifacts] Toute nouvelle syntaxe de référence se répercute dans `extract_artifact_ids` (artifacts/parser.py) ET dans un test de refcount → sinon l'artefact tombe à refcount 0 et est purgé (cas `artifact://uuid` en puce).
- [automations] Le contenu courant d'un document vit dans `document_version.content` à `version_number = document.version` (JOIN), pas dans `document`.
- [templates] Lire le code existant avant de bâtir du neuf (la galerie distante existe : `templates/gallery.py`). Dans `importer.py`, calculer le diff AVANT le check no_op, sinon le ré-import est bloqué après suppression des types.
- [logs] Le label Loki de la stack est `compose_project="deploy"`, pas `"docflow"` → une requête sur le mauvais label rend un résultat vide, qui ressemble à « pas de log » plutôt qu'à « mauvaise question ».
- [mld] Une fonction pure écrite, exportée et testée peut n'être appelée par personne (`sidesFor`) → vérifier l'usage réel, pas seulement l'existence ; un test d'unité ne prouve pas le câblage.
- [frontend] `npx tsc --noEmit` à la racine ne vérifie RIEN (`tsconfig.json` a `"files": []` et délègue aux références) → utiliser `npx tsc -b`, sinon des erreurs de type dans `src/test/` passent inaperçues.
- [backlog] Les valeurs de `statut` sont définies PAR type fonctionnel (`epic` a `a_cadrer`/`cadre` et pas de `en_review`) → un filtre `where statut in [...]` en manque silencieusement ; énumérer les objets et filtrer côté client, sinon on conclut « lot fini » à tort (15 tickets ouverts vus comme 9).
