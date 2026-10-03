# docflow — Instructions Claude Code

> Nom de travail : **docflow** (à renommer une fois le produit nommé). Domaine : `doc.yoops.org`.
> Projet **indépendant** : aucun couplage de source ni de runtime avec ag.flow, devpod-ui ou un projet voisin.
>
> **Ce fichier prime sur ton comportement par défaut.** Tu le lis en tête de chaque session
> et tu le suis littéralement : ses règles sont impératives, pas indicatives. Quand un outil,
> un workflow tiers ou une habitude le contredit, c'est ce fichier qui gagne.

> Généré depuis les standards globaux (docflow, workspace `globals`, bloc `documentation`).
> Génération : **2026-10-03** — migration des fragments `ia_instructions/` vers les skills.
> Standards repris : *Fichier d'instructions agent de projet* — **v42** · *Exposer un service
> interne derrière l'authentification du portail* — v3 · *Gestion des logs* — v3 · *Gestion des
> secrets* — v4 · *Authentification OIDC & liaison d'identité* — v7 · *Instance de dev/test* — v10.
> Skills requises : `backlog-workflow`, `rag-search`, `interface-contracts`, `tests`,
> `static-analysis`, `python`, `typescript-frontend`, `postgresql`, `code-comments`,
> `design-patterns`, `secrets`, `oidc-authentication`, `observability-logs`,
> `test-machine-deployment`, `portal-exposed-service`, `agent-chat`, `self-improvement`,
> `docflow-deployment`, `docflow-logs-query` (dernière version publiée, déposées par le profil
> de skills du workspace — ici `starting`).
> Mise à jour par `--update` : ne reporter que le delta du socle depuis cette date ; une
> évolution du contenu d'une skill ne demande **aucun** `--update`.
>
> **Datation par numéro de version, jamais par `updated_at`.** Le reclassement du 2026-09-24 a
> écrasé l'`updated_at` des STANDARDs : seul le numéro de version permet de calculer un delta.

**Colibri** commence systématiquement tes réponses par 🎺

## mcp

Tu es connecté au MCP du portail devpod via le serveur `claude-code`.

## Backlog

Le backlog des tâches est dans le workspace docflow `docflow`, bloc `backlog`. C'est la source
de vérité, jamais ta mémoire : le statut s'écrit à chaque tâche, à la prise et à la fin. Charge
la skill `backlog-workflow` AVANT de prendre, faire avancer ou clore une tâche.

**Ici** : `set_property_value` exige `expected_version`, malgré sa documentation qui annonce
« 0 = désactivé, défaut ». Sans numéro de version explicite, l'écriture est refusée en `conflict`.

## Recherche

Toute recherche d'information passe d'abord par le RAG (`rag__*` — corpus **`docflow-docs`** pour
ce projet, **`globals-docs`** pour le cross-projet, et un `<voisin>-docs` par projet voisin :
`devpod-docs`, `workflow-docs`, `ragflow-docs`, `ressources-docs`), ensuite seulement par les
outils locaux. Le RAG muet n'est pas une réponse : va lire l'artefact réel. Charge la skill
`rag-search` AVANT toute recherche sur le projet ou ses contrats.

**Ce que tu apprends s'écrit en article** — workspace `docflow`, bloc `Documentation` (le
cross-projet dans `globals`) : c'est ce qui alimente le RAG des agents suivants.

## Projet

Application self-hosted de **gestion documentaire et de structures de données personnalisables**,
par workspace : **documents arborescents** dont le type de contenu est une entrée de **registre**,
jamais une condition chez l'appelant ; **types fonctionnels définis par l'utilisateur** — **rien
n'est câblé en dur**, ne code jamais un slug de type en littéral ; **propriétés typées**, le
**statut** n'étant qu'une propriété `restricted_list` ; un **serveur MCP** exposant le store,
interface de première classe et pas un extra.

Spec : `specs/00_README.md` → milestones, exécutés **dans l'ordre**. **Lire `01`, `02`, `02b`, `03`
avant tout code** ; `03_PITFALLS.md` contient des **exigences**, pas des conseils.

**Hors périmètre / couplages interdits.** Aucun import, aucun appel direct, aucun schéma partagé
avec ag.flow, devpod-ui ou un projet voisin. Une convention d'un dépôt voisin ne s'importe
**jamais** sans vérifier qu'elle s'applique ici.

**Ton** : réponses claires et concises, pas de long discours. Simple et direct.

## Stack & où vit l'état

**Décision posée, non rediscutable** : l'état vit dans **PostgreSQL**, dans une instance **dédiée
à la stack** (`postgres:16-alpine`, base `docflow`, déclarée dans `deploy/docker-compose.yml`).
Pas de schéma invité chez un voisin — les cycles de sauvegarde et de migration restent découplés.
Ne propose pas d'en changer « pour simplifier ». Exigence de fond : **un incident en cours
d'écriture ne doit jamais corrompre l'existant** — d'où « une opération de cycle de vie = une
transaction », et ça se teste.

- **Backend** : Python 3.12 + FastAPI + pydantic v2 / pydantic-settings + **asyncpg** + authlib
  (OIDC) + httpx + structlog JSON + pytest. Mots de passe argon2.
- **Persistance** : une base, deux plans logiques (instance / contenu scopé workspace). Schéma
  versionné sous `backend/migrations/`, appliqué par une primitive `apply` **idempotente**.
- **Auth** : bootstrap admin local (break-glass permanent) puis OIDC Keycloak
  (`security.yoops.org`, realm `yoops`, client `docflow`). RBAC `admin` / `superadmin`.
- **Secrets** : Harpocrate via références `${vault://...}` — **jamais en clair**.
- **Frontend** : Vite + React + TypeScript strict + TanStack Query + Tailwind v4 + shadcn/ui +
  i18next + Vitest. **En place et conséquent**, ce n'est plus un chantier.
- **MCP** : serveur exposant le store en lecture/écriture sous le même RBAC.

## Commandes essentielles

```bash
# Installer      cd backend && uv sync                          | cd frontend && npm install
# Lancer         uv run uvicorn docflow.app:app --reload  :8000 | npm run dev          :5173
# Tester         cd backend && uv run pytest -v                 | npm run test
# Style          cd backend && uv run ruff check src/ tests/    | (aucun linter JS ici)
# Types          cd backend && uv run mypy src/                 | npx tsc -b
# Construire                                                      cd frontend && npm run build
# Migrations     cd backend && uv run python -m docflow.db.apply   (idempotent)
# Stack locale   docker compose -f deploy/docker-compose.yml up -d
```

### ⚠ Divergence assumée vs la skill `typescript-frontend`

**Ici, `npx tsc -b` depuis `frontend/`, jamais `tsc --noEmit`, et pas d'ESLint.** La skill prescrit
les deux : ils sont **inopérants dans ce dépôt**. `tsconfig.json` porte `"files": []` et délègue à
des références — `--noEmit` ne vérifie donc **rien** — et ESLint n'existe ni en configuration ni en
dépendance. Un agent qui suit la skill croit avoir vérifié ses types sans rien avoir vérifié.

## Layout du code

```
backend/migrations/   un .sql numéroté IMMUABLE par migration
backend/src/docflow/  app.py · config/ db/ secrets/ · auth/ oidc/ · workspaces/ types/
                      properties/ documents/ blocks/ · codecs/ (registre de types de
                      contenu) · mcp/ schemas/
frontend/src/         components/ pages/ hooks/ locales/ styles/ · lib/contentSurfaces/
                      (registre de surfaces, miroir front des codecs) · lib/canvas/ lib/mld/
deploy/               Dockerfile (AUCUN secret) · compose dev & prod · DEPLOY.md
```

## Sécurité (non négociable)

Ces interdits coupent un commit. Tu ne dois pas avoir à charger une skill pour les connaître.

- Aucun secret en argument de construction, en `ENV` de Dockerfile, en couche d'image, en log,
  dans le dépôt, **ni en colonne claire**. `client_secret` OIDC = référence `${vault://...}`.
- **Garde-fou anti-lock-out** : le dernier admin local connectable par mot de passe ne peut être
  ni désactivé ni supprimé. C'est un **test**, pas une intention.
- **Fail closed** : aucun endpoint métier sans authentification ; aucune ressource d'un workspace
  accessible sans en avoir le droit.
- **Entrées utilisateur validées** avant tout usage en chemin, identifiant ou nom d'hôte
  (slugs : `^[a-z0-9][a-z0-9_-]*$`).

## Quand charger une skill

Les skills ne sont **PAS** chargées d'office. Chacune a son déclencheur : quand il se produit,
charge la skill **AVANT** d'écrire quoi que ce soit — pas après, pas « si ça semble utile ».

| Tu t'apprêtes à… | Charge d'abord |
|---|---|
| prendre, faire avancer ou clore une tâche du backlog | la skill `backlog-workflow` |
| chercher une information sur le projet, ses voisins ou ses contrats | la skill `rag-search` |
| définir ou consommer une route, un webhook, un event, un format d'échange | la skill `interface-contracts` |
| modifier un fichier `.py` sous `backend/` | la skill `python` **+** `ia_instructions/10_python.md` |
| modifier un fichier sous `frontend/src/` | la skill `typescript-frontend` **+** `ia_instructions/10_typescript.md` |
| écrire ou modifier une migration, ou une requête SQL | la skill `postgresql` **+** `ia_instructions/10_postgresql.md` |
| écrire ou modifier un test | la skill `tests` |
| lancer le style ou les types avant de déclarer terminé | la skill `static-analysis` |
| écrire ou modifier un commentaire de code | la skill `code-comments` |
| introduire un registre, une fabrique ou tout autre patron | la skill `design-patterns` |
| manipuler, stocker ou résoudre un secret | la skill `secrets` |
| toucher à l'authentification OIDC ou à la liaison d'identité | la skill `oidc-authentication` |
| écrire une ligne de journal, ou instrumenter du code | la skill `observability-logs` |
| **interroger** les journaux de l'instance | la skill `docflow-logs-query` |
| déployer, livrer, diagnostiquer sur une machine de test, ou toucher à `dev-deploy.sh` | les skills `test-machine-deployment` **et** `docflow-deployment` |
| ajouter ou modifier un service exposé, ou sa déclaration à l'annuaire | la skill `portal-exposed-service` |
| appeler, inviter ou répondre à un autre agent ; voir `[TCHAT] nouveau message` | la skill `agent-chat` |
| corriger une erreur que l'utilisateur t'a signalée, ou une erreur qui se répète | la skill `self-improvement` |
| créer, régénérer ou mettre à jour ce fichier | la skill `instructions-file-generation` |

Les trois `ia_instructions/10_*.md` **ne sont pas des doublons** : ce sont les résidus que leur
skill partagée ne couvre pas encore (commandes exactes, invariants nommés, pièges du dépôt). Ils
restent jusqu'à ce que les skills soient complétées — ne les supprime pas par réflexe.

## Repli — skill absente

Une skill de la table ci-dessus introuvable se **signale** : tu ne devines JAMAIS ce qu'elle
contenait.

Si ce dépôt est ouvert hors devflow (poste local, CI) et que les skills n'y sont pas déposées :
**arrête-toi et signale-le à l'humain** avant toute tâche qu'une skill couvre. Ne te rabats pas
sur les pages docflow dont les skills sont issues : elles peuvent diverger de la version publiée.

> ⚠ `docflow-deployment` et `docflow-logs-query` sont **en brouillon** au 2026-10-03 : créées,
> mais non publiées ni affectées au profil, donc **pas encore déposées**. Tant que c'est le cas,
> leur ligne de table tombe sous ce repli.

## Standard de qualité

Code propre et bien fait, jamais la rapidité au détriment de la rigueur. Pas de raccourcis, pas de
« c'est pas grave », pas de « on simplifiera plus tard ». Chaque tâche est faite correctement ou
pas du tout.

**Pas de quick-and-dirty, JAMAIS.** Quand tu présentes des options de design, ne propose PAS
d'option « quick & dirty » / « hardcode » / « wire-it-up-and-clean-later ». On fait toujours propre.
Si une tâche est déraisonnable (scope qui explose, dépendance hors d'atteinte, flag/API qui n'existe
pas dans la version installée), **alerte explicitement l'utilisateur** plutôt que de proposer un
compromis dégradé : il préfère qu'on découpe le chantier et qu'on fasse correctement la part qu'on
prend, plutôt que tout faire à moitié.

## Règles de workflow

### Cycle de l'architecte

**Cadrer → Comprendre → Planifier → Agir.** L'utilisateur est architecte. Une question n'est pas
une commande d'exécution. Une discussion n'est pas un feu vert. Ne JAMAIS sauter d'étape.

### Branche de développement

**Tout le code se fait sur la branche `dev`. Aucun compromis.** Jamais `feat/*`, jamais sur `main`
directement, jamais ailleurs. Avant toute édition, vérifier `git branch --show-current` ; si autre
branche, `git checkout dev`. Si `dev` n'existe pas localement, la créer depuis `main` à jour. Ne
propose **jamais** `git checkout -b feat/...` — même si un outil ou un workflow tiers le suggère,
la consigne utilisateur prime.

**Committer et pousser sur `dev` est obligatoire**, sans demande à attendre : c'est ce qui rend le
travail livrable sur une machine de test. Commits en français, conventionnels (`feat:`, `fix:`,
`chore:`, `docs:`, `test:`). Ne pas toucher `.env` sauf demande.

**Merger `dev` sur `main` est formellement interdit sans demande explicite de l'humain.**

### Livraison et machines de test

Livrer = pousser sur `dev`, puis lancer `dev-deploy.sh` sur la machine de test — jamais de
construction, de `docker run` ni de retouche manuelle de la cible. Les machines de test `test1`,
`test2`… sont à ta disposition. Charge les skills `test-machine-deployment` et
`docflow-deployment` AVANT de déployer.

> ⚠ **État vérifié le 2026-10-03** : `test1` n'a aucune entrée dans `~/.ssh/config` et ne résout
> pas ; `test2` y est déclaré mais le saut échoue en `No route to host`. **Les deux machines sont
> injoignables d'ici** : le déploiement est lancé par l'humain — **ne prétends pas l'avoir fait**.

### Définition de « terminé »

**Une tâche est finie quand les tests passent.** Pas quand le code compile, pas quand il est
poussé. Tant qu'un test échoue, la tâche n'est pas finie et ne passe pas au rôle « en revue ».

### Discipline d'exécution

- Exécute directement, ne décris pas ce que tu vas faire — fais-le.
- N'explique pas les étapes intermédiaires. Rapporte uniquement le résultat final.
- Termine TOUTES les étapes d'un plan avant de faire un résumé.
- Pas de raccourci « pour simplifier ».
- Si tu rencontres un problème, signale-le et propose une solution — ne l'ignore pas silencieusement.

### Leçons de travail — erreurs réelles à ne pas refaire

- **Chercher avant de créer.** Avant de créer une table, un module, un document ou une règle,
  cherche son nom : la pièce existe déjà plus souvent qu'on ne le croit.
- **Interroger le système plutôt que déduire de la doc.** La documentation dit ce qui est illustré,
  pas ce qui est permis. Quand un accès existe (bac à sable, `--help`, requête réelle), interroge-le.
  Ce qui se vérifie ne se déduit pas ; une déduction s'annonce comme telle.
- **Exclure les zones littérales des transformations.** Toute transformation programmatique d'un
  document épargne blocs de code, citations et exemples — puis se vérifie en comparant ces zones à
  leur source, caractère par caractère.
- **Ne lancer que les outils déclarés.** Avant un outil de mise en forme ou de correction, vérifie
  qu'il est déclaré dans le dépôt ; à défaut, tiens-t'en à ceux qui le sont.
- **Vérifier la cible avant d'agir.** Établis sur quoi tu agis — machine, dépôt, branche,
  environnement — et que c'est bien l'endroit que l'utilisateur décrit.
- **Un symptôme à causes multiples ne désigne pas sa cause.** N'en nomme une qu'après avoir écarté
  les autres en mesurant, une variable à la fois, assez de fois pour qu'un défaut intermittent ne
  décide pas à ta place. Une contestation de l'utilisateur est une donnée : elle vaut souvent mieux
  que ta déduction.
- **Relire après écriture.** Un stockage normalise ce qu'on lui donne : relis et compare à ce que tu
  voulais écrire, pas seulement au succès de l'appel.
- **Vérifier le résultat, jamais le code de retour.** Un « succès », un test vert, une sortie à zéro
  ne prouvent pas que la chose voulue s'est produite.

## Auto-amélioration

Une erreur corrigée devient une leçon dans `LESSONS.md`. Charge la skill `self-improvement` quand
l'utilisateur te corrige ou qu'une erreur se répète.

## Tchat agents

En début de session, inscris-toi : `agent_register(session=<ta session tmux>, command=<ce qui t'a
lancé>)`. Jamais de polling : à la vue du marqueur `[TCHAT] nouveau message` dans ton stdin, comme
avant d'appeler, d'inviter ou de répondre à un autre agent, charge la skill `agent-chat`.

### ⚠ Divergence assumée vs la skill `agent-chat`

**Vérifié le 2026-10-03 par l'appel réel** : `tchat_*` et `agent_register` **sont servis**, et
`message_send` est **retiré du catalogue** — aucun canal de repli. Mais le serveur les réserve à une
session d'agent de workspace (clé API) : **depuis une session CLI l'appel est refusé, joindre un
agent est impossible**. La tâche qui l'exige se signale en fin de tour ; elle ne se contourne ni par
`session_open`, ni par un détour. La skill dit l'inverse (« aucun credential à gérer ») et prescrit
de vérifier via la gateway — **cette méthode a produit une conclusion fausse** : `list_backends`
liste des backends, jamais leurs primitives. **Seul l'appel tranche ; un refus d'autorisation n'est
pas une absence.**

## Outils de l'agent

Par **fonction**, avec son déclencheur : la fonction est l'invariant, l'outil n'en est qu'une
implémentation. Un outil non déclenché au bon moment ne sert à rien.

| Fonction | Déclencheur | Ici |
|---|---|---|
| Doc à jour d'une bibliothèque | avant d'écrire du code qui l'utilise | **Context7** |
| Contrat réel d'une CLI | avant tout appel à une CLI externe | **`--help` first** — le binaire installé fait foi, aucune alternative |
| Navigation sémantique | avant un refactor, pour trouver les usages | **pas d'équivalent ici** (Serena absent) : `Grep` structuré ou l'agent `Explore` |
| Méthodes de travail | plan, exécution, débogage, TDD | **pas d'équivalent ici** : les skills Superpowers ne sont PAS déposées — appliquer la méthode à la main |
| Revue | >3 fichiers ou >100 lignes | **`/code-review`**, et `/security-review` sur un diff sensible |
| Commit | à chaque tâche livrée, sans attendre de demande | à la main, format français conventionnel |

## Vérification avant validation

Avant de déclarer une tâche terminée, **toutes** ces étapes sont obligatoires :

1. Le style, les types et la construction passent — back : `ruff check` + `mypy src/` ; front :
   `npx tsc -b` + `npm run build`.
2. Le cas nominal est testé — `uv run pytest` et/ou `npm run test`, pas une vérification à l'œil.
3. Les imports ajoutés existent réellement.
4. Aucune régression sur les fichiers modifiés.
5. **La part de checklist de chaque skill touchée est cochée** — charge `python`,
   `typescript-frontend`, `postgresql`, `tests`, `static-analysis` selon ce que tu as modifié. En
   particulier : une migration s'applique sur base vierge **ET** existante, `apply` reste idempotent
   rejoué, et les flags d'une CLI externe ont été vérifiés contre `--help`.
6. Aucun secret ni clé dans le diff (`git diff` relu sous cet angle).
7. Les tests passent **là où ils sont le plus révélateurs** — sur une machine de test dès qu'elle
   peut révéler davantage que le local.

## Notifications de capacités

Quand tu invoques une capacité outillée (skill, commande, extension), affiche systématiquement un
marqueur **avant** d'exécuter :

> **`🟢 SKILL`** → *nom-de-la-capacité* — raison en une phrase

Ce qui compte n'est pas le mot employé : c'est que l'invocation soit **annoncée avant** de produire
son effet, sans quoi l'action de l'agent n'est ni lisible ni auditable.

## Services publiés à l'annuaire

| Service | Rôle | Port (variable) | Déclaration |
|---|---|---|---|
| `docflow` | L'application elle-même (`doc.yoops.org`) | `APP_DEV_PORT` | **obligatoire** |

Déclaration à la fin du déploiement, après le smoke — **déjà implémentée dans `dev-deploy.sh`**.
Authentification par **code TOTP** (primitive MCP `totp_code`), jamais le jeton admin partagé,
**jamais journalisée ni passée en argv**. Geste : skill `portal-exposed-service`.
