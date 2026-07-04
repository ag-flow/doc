# Bugs docflow — inventaire

Tour complet de l'application (backend, frontend, migrations, déploiement) mené le **2026-07-03**.
Chaque bug a **sa propre fiche** dans ce répertoire. **Aucun bug n'a été corrigé** — les fiches documentent le défaut, sa reproduction et une piste de correction.

Méthode : 6 revues en parallèle (auth/sécurité, DB/secrets/backup, domaine documents, intégrations, frontend, déploiement) ; les findings critiques ont été re-vérifiés par relecture directe du code.

## Convention de nommage

`<ZONE>-<NN>-<slug>.md` — zones : `AUTH` (auth/RBAC/MCP), `DOC` (domaine documents/vues), `DB` (persistance/backup/secrets), `INT` (intégrations), `DEP` (déploiement), `FE` (frontend).

## Modèle Claude recommandé par bug

La colonne **Modèle** de chaque tableau propose le modèle à utiliser pour le correctif, selon cette logique :

- **Fable** — correctifs où une solution naïve réintroduit le bug, décisions d'architecture / sémantique RBAC, sécurité subtile (crypto/auth), concurrence & async délicate.
- **Opus** — correctifs complexes mais bien cadrés : multi-fichiers, logique non triviale, refactor, intégrité du versioning frontend.
- **Sonnet** — correctifs localisés / mécaniques : config, doc, une seule fonction, regex, ajout de validation, clé manquante.

Récapitulatif : **Fable** 6 bugs · **Opus** 22 bugs · **Sonnet** 44 bugs.

## Bugs critiques

| ID | Titre | Fichier principal | Modèle |
|----|-------|-------------------|--------|
| [AUTH-01](AUTH-01-oidc-callback-sans-verification-signature.md) | Callback OIDC émet un JWT sans vérifier la signature de l'id_token | `oidc/router.py`, `oidc/service.py` | **Fable** |
| [DOC-01](DOC-01-vues-renumerotation-placeholders-cassee.md) | Renumérotation des placeholders `$n` cassée dans le moteur de vues | `views/service.py` | **Fable** |
| [DOC-02](DOC-02-reparentage-sans-anti-cycle.md) | Reparentage de document sans détection de cycle → boucle infinie Postgres | `documents/service.py` | **Opus** |
| [DOC-03](DOC-03-create-document-block-id-cross-workspace.md) | `create_document` accepte un `block_id` d'un autre workspace | `documents/service.py` | **Opus** |
| [DB-01](DB-01-pool-asyncpg-cross-loop-git-sync.md) | Pool asyncpg utilisé depuis un autre event loop (git_sync) | `backup/worker.py` | **Fable** |
| [DB-02](DB-02-reconciliation-orphelins-suppression-massive.md) | Réconciliation orphelins : suppression massive de workspaces non modifiés | `backup/git_sync.py` | **Fable** |
| [DB-03](DB-03-git-push-env-echoue.md) | ✅ `origin.push(env=)` fait échouer tous les push git | `backup/git_sync.py` | **Sonnet** |
| [DB-04](DB-04-export-json-uuid-et-valeurs-falsy.md) | ✅ Export JSON : `TypeError` sur UUID + valeurs falsy écrasées | `backup/git_sync.py` | **Sonnet** |
| [FE-01](FE-01-editeur-contenu-autre-document.md) | Éditeur affiche/sauvegarde le contenu d'un autre document | `MarkdownEditor.tsx`, `DocumentEditor.tsx` | **Opus** |
| [FE-02](FE-02-conflictresolver-fusion-ecrasee.md) | ConflictResolver : la fusion est écrasée par la sauvegarde suivante | `DocumentEditor.tsx` | **Opus** |

## Bugs majeurs

| ID | Titre | Fichier principal | Modèle |
|----|-------|-------------------|--------|
| [AUTH-02](AUTH-02-oidc-liaison-email-sans-email-verified.md) | Liaison de compte OIDC par email sans `email_verified` | `oidc/service.py` | **Opus** |
| [AUTH-03](AUTH-03-anti-lockout-demotion-is-admin.md) | Anti-lock-out contourné : démotion `is_admin` du dernier admin | `admin/users/service.py` | **Opus** |
| [AUTH-04](AUTH-04-anti-lockout-devalidation-et-count.md) | Anti-lock-out : dévalidation + COUNT qui ignore `validated` | `auth/lockout.py`, `admin/users/service.py` | **Opus** |
| [AUTH-05](AUTH-05-scopes-api-key-non-appliques.md) | Scopes d'API key non appliqués sur documents/properties/types | `documents/router.py`, `properties/router.py`, `types/router.py` | **Opus** |
| [AUTH-06](AUTH-06-setup-race-plusieurs-admins.md) | Race au setup : plusieurs admins créés dans la fenêtre d'init | `setup/service.py` | **Opus** |
| [AUTH-07](AUTH-07-require-admin-ne-verifie-pas-is-admin.md) | `require_admin` ne vérifie aucun droit admin | `auth/deps.py` (+ surfaces MCP/admin) | **Fable** |
| [INT-01](INT-01-path-traversal-template-slug-gallery.md) | Path traversal / écriture arbitraire via `template_slug` (galerie) | `templates/gallery.py`, `templates/router.py` | **Sonnet** |
| [INT-02](INT-02-automation-debounce-famine.md) | Debounce d'automation : famine de tout le workspace | `automations/worker.py` | **Opus** |
| [INT-03](INT-03-mcp-outils-ecriture-identite-superadmin.md) | Outils MCP d'écriture exécutés sous l'identité du superadmin système | `mcp/server.py` | **Opus** |
| [DOC-04](DOC-04-changement-type-valeurs-orphelines.md) | Changement de type : valeurs de propriétés orphelines conservées | `documents/service.py` | **Opus** |
| [DOC-05](DOC-05-parser-references-uuid-laxiste.md) | Parser de références : regex UUID laxiste → 500 + doublons de casse | `references/parser.py`, `references/service.py` | **Sonnet** |
| [DOC-06](DOC-06-create-document-references-non-indexees.md) | `create_document` n'indexe pas les références du contenu initial | `documents/service.py` | **Sonnet** |
| [DOC-07](DOC-07-gardes-fk-mortes-cascade-0011.md) | Gardes FK mortes depuis 0011 → suppressions silencieusement destructrices | `properties/service.py`, `blocks/service.py`, `types/service.py` | **Fable** |
| [DOC-08](DOC-08-vues-collision-slug-partagee-privee.md) | Vues : collision de slug partagée/privée → résolution indéterminée | `views/service.py` | **Opus** |
| [DB-05](DB-05-croniter-dependance-absente.md) | ✅ `croniter` absent des dépendances → jobs cron jamais exécutés | `backup/worker.py`, `pyproject.toml` | **Sonnet** |
| [DB-06](DB-06-pg-dump-mot-de-passe-argv.md) | ✅ `pg_dump` : mot de passe Postgres visible dans `ps` (argv) | `backup/db_dump.py` | **Sonnet** |
| [DB-07](DB-07-pat-git-en-clair-git-config.md) | PAT git persisté en clair dans `.git/config` | `backup/worker.py`, `backup/git_sync.py` | **Opus** |
| [DB-08](DB-08-run-running-orphelin-job-bloque.md) | ✅ Run `running` orphelin après crash → job bloqué définitivement | `backup/worker.py` | **Sonnet** |
| [DB-09](DB-09-job-echec-retry-30s.md) | ✅ Job en échec : retry toutes les 30 s au lieu de l'intervalle | `backup/worker.py` | **Sonnet** |
| [DB-10](DB-10-ftps-port-990-incompatible.md) | ✅ FTPS : port par défaut 990 incompatible avec le TLS explicite | `backup/db_dump.py` | **Sonnet** |
| [DB-11](DB-11-url-ssh-git-malformee.md) | ✅ URL SSH git malformée (`git@host/repo` au lieu de `:`) | `backup/worker.py` | **Sonnet** |
| [DEP-01](DEP-01-identifiants-admin-bootstrap-morts.md) | ✅ Identifiants admin bootstrap morts affichés par le déploiement | `scripts/dev-deploy.sh`, `deploy/DEPLOY.md` | **Sonnet** |
| [DEP-02](DEP-02-scripts-sql-doublons-divergents.md) | ✅ `scripts/*.sql` : copies périmées et divergentes des migrations | `scripts/*.sql` | **Sonnet** |
| [DEP-03](DEP-03-ports-0000-contournent-tls.md) | ✅ Ports publiés sur `0.0.0.0` contournant le TLS | `deploy/docker-compose*.yml` | **Sonnet** |
| [DEP-04](DEP-04-image-tourne-en-root.md) | ✅ L'image de prod tourne en root | `deploy/Dockerfile` | **Sonnet** |
| [DEP-05](DEP-05-procedure-restore-cassee.md) | Procédure de restauration DEPLOY.md non fonctionnelle/destructrice | `deploy/DEPLOY.md` | **Sonnet** |
| [FE-03](FE-03-refetch-arriere-plan-verrou-optimiste.md) | Refetch arrière-plan : verrou optimiste contourné + titre perdu | `DocumentEditor.tsx` | **Opus** |
| [FE-04](FE-04-login-401-recharge-page.md) | Login : 401 recharge la page au lieu d'afficher l'erreur | `lib/api.ts`, `Login.tsx` | **Opus** |
| [FE-05](FE-05-propriete-bool-premier-toggle.md) | Propriété `bool` : le premier toggle n'est jamais persisté | `PropertyField.tsx`, `useFieldState.ts` | **Opus** |
| [FE-06](FE-06-secretinput-fuite-secret-changement-mode.md) | SecretInput : secret exposé en clair lors d'un changement de mode | `SecretInput.tsx` | **Sonnet** |
| [FE-07](FE-07-issuperadmin-atob-base64url.md) | `isSuperAdmin()` : `atob` échoue sur JWT base64url → UI admin masquée | `lib/api.ts` | **Sonnet** |
| [FE-08](FE-08-templatelist-course-openedit.md) | TemplateList : course dans `openEdit` → mauvais YAML sauvegardé | `TemplateList.tsx` | **Sonnet** |
| [FE-09](FE-09-backlinkspanel-mauvais-bloc.md) | BacklinksPanel : navigation avec le mauvais bloc/workspace | `BacklinksPanel.tsx` | **Opus** |

## Bugs mineurs

| ID | Titre | Fichier principal | Modèle |
|----|-------|-------------------|--------|
| [AUTH-08](AUTH-08-jwt-algorithms-non-epingles.md) | ✅ `decode_token` n'épingle pas la liste d'algorithmes | `auth/jwt.py` | **Sonnet** |
| [AUTH-09](AUTH-09-login-enumeration-timing.md) | ✅ Oracle d'énumération d'utilisateurs sur `/auth/login` (timing) | `auth/router.py` | **Sonnet** |
| [INT-04](INT-04-mcp-messages-sans-auth.md) | `POST /api/mcp/messages` sans dépendance d'auth | `mcp/router.py` | **Opus** |
| [INT-05](INT-05-webhook-sentinelle-now.md) | Collision de sentinelle `"now()"` dans l'UPDATE webhook | `webhooks/service.py` | **Sonnet** |
| [INT-06](INT-06-ssrf-urls-administrees.md) | SSRF via URLs administrées (webhooks/automations/contracts/galerie) | `webhooks/`, `automations/`, `contracts/`, `templates/` | **Opus** |
| [INT-07](INT-07-health-fuite-exception.md) | `/health` fuit `str(exc)` dans la réponse 503 | `app.py` | **Sonnet** |
| [DOC-09](DOC-09-update-document-keyerror-slug.md) | `update_document` : `KeyError` sur conflit de slug lors d'un déplacement | `documents/service.py` | **Sonnet** |
| [DOC-10](DOC-10-workspace-archive-modifiable.md) | Workspace archivé encore entièrement modifiable | `workspaces/service.py`, `db/helpers.py` | **Opus** |
| [DOC-11](DOC-11-viewupdate-layout-non-valide.md) | `ViewUpdate.layout` non validé → 500 au lieu de 422 | `views/service.py` | **Sonnet** |
| [DOC-12](DOC-12-allowed-types-parent-id-cross-workspace.md) | `allowed_types` avec `parent_id` : fuite inter-workspace | `documents/block_ops.py` | **Sonnet** |
| [DOC-13](DOC-13-webhook-fire-create-task-gc.md) | `_fire` webhooks : `asyncio.create_task` sans référence conservée | `documents/router.py` | **Sonnet** |
| [DOC-14](DOC-14-incoherences-domaine-diverses.md) | Incohérences domaine diverses (template bloc, cursor, bloc_ref FK, default NULL) | `documents/`, `views/`, `properties/` | **Opus** |
| [DB-12](DB-12-cle-ssh-world-readable.md) | ✅ Clé privée SSH : fenêtre world-readable, jamais supprimée | `backup/worker.py` | **Sonnet** |
| [DB-13](DB-13-sftp-autoaddpolicy-host-key.md) | ✅ SFTP : `AutoAddPolicy`, host key jamais vérifiée | `backup/db_dump.py` | **Sonnet** |
| [DB-14](DB-14-apply-sans-verrou.md) | ✅ `apply()` sans verrou : course entre instances au boot | `db/apply.py` | **Sonnet** |
| [DB-15](DB-15-nom-variable-encryption-key.md) | ✅ Messages d'erreur citant `DOCFLOW_ENCRYPTION_KEY` au lieu de `ENCRYPTION_KEY` | `vault/router.py`, `webhooks/service.py` | **Sonnet** |
| [DEP-06](DEP-06-dev-env-sans-encryption-key.md) | `/data/.env` de dev sans `ENCRYPTION_KEY` (divergence dev/prod) | `scripts/dev-deploy.sh` | **Sonnet** |
| [DEP-07](DEP-07-pg-dump-version-client-flottante.md) | Version de `pg_dump` non maîtrisée dans l'image (base flottante) | `deploy/Dockerfile` | **Sonnet** |
| [DEP-08](DEP-08-prod-deploy-source-env-docker.md) | `prod-deploy.sh` source le `.env` format docker dans bash | `deploy/prod-deploy.sh` | **Sonnet** |
| [DEP-09](DEP-09-port-dev-8080-vs-8000.md) | Port de dev : la doc dit `:8080`, uvicorn écoute sur 8000 | `CLAUDE.md`, `vite.config.ts` | **Sonnet** |
| [FE-10](FE-10-double-submit-entree-creation.md) | Double-submit par Entrée dans les dialogues de création | `AddDocumentDialog.tsx`, `DocumentChildrenPanel.tsx` | **Sonnet** |
| [FE-11](FE-11-linksearchpopup-spinner-bloque.md) | LinkSearchPopup : spinner bloqué et réponses hors-ordre | `LinkSearchPopup.tsx` | **Sonnet** |
| [FE-12](FE-12-labeltoslug-supprime-chiffres.md) | `labelToSlug` supprime les chiffres | `lib/slug.ts` | **Sonnet** |
| [FE-13](FE-13-i18n-hint-modele-contenu-vide.md) | i18n : hint du modèle de contenu vidé par l'interpolation | `TypePropertiesPanel.tsx` | **Sonnet** |
| [FE-14](FE-14-typesadmin-fragments-sans-key.md) | TypesAdmin : fragments sans `key` | `TypesAdmin.tsx` | **Sonnet** |
| [FE-15](FE-15-blocsadmin-export-sans-gestion-erreur.md) | BlocsAdmin `handleExport` : erreurs HTTP non gérées | `BlocsAdmin.tsx` | **Sonnet** |
| [FE-16](FE-16-pub-non-proxifie-dev.md) | `/pub` non proxifié en dev | `vite.config.ts`, `lib/api.ts` | **Sonnet** |
| [FE-17](FE-17-logout-cache-non-purge.md) | Logout : cache TanStack Query non purgé | `Sidebar.tsx` | **Sonnet** |
| [FE-18](FE-18-apikeys-scopes-perimes.md) | ApiKeysPage : scopes affichés périmés après sauvegarde | `ApiKeysPage.tsx` | **Sonnet** |

---

**Totaux** : 10 critiques, 33 majeurs, 29 mineurs — 72 bugs documentés.
**Répartition modèles** : Fable 6 · Opus 22 · Sonnet 44.
