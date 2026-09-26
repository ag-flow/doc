# docflow — Instructions Claude Code

> Nom de travail : **docflow** (à renommer une fois le produit nommé). Domaine de travail : `doc.yoops.org`.
> Projet **indépendant** d'ag.flow, devpod-ui (aucun couplage runtime ni de source).

> Généré depuis les standards globaux (docflow, workspace `globals`, bloc `documentation`).
> Génération : **2026-09-20**. Dernier `--update` : **2026-09-26**.
> Standards repris (titre — version du document au moment du report) : *Fichier
> d'instructions agent de projet* — v36 · *Exposer un service interne derrière
> l'authentification du portail* — v3 (rév. 16/09/2026) · *Gestion des logs* — v3 ·
> *Gestion des secrets* — v4 (rév. 2026-09-20) · *Authentification OIDC & liaison
> d'identité* — v7 · *Instance de dev/test* — v10.
> Mise à jour par `--update` : ne reporter que le delta depuis cette date.
>
> **Datation par numéro de version, et non par `updated_at`.** Le reclassement du
> 2026-09-24 (reprise T3) a écrasé l'`updated_at` des STANDARDs, et aucun d'eux ne
> porte de date de révision interne systématique : la date de modification ne peut
> donc plus servir à calculer un delta. Le numéro de version du document, lui, est
> intact — `--update` compare désormais des versions, pas des dates.
>
> Avant le 2026-09-20 le fichier n'avait pas de provenance : la conformité a été
> **revérifiée intégralement**, pas déduite d'un delta.

**Ce fichier prime sur ton comportement par défaut.** Tu le lis en tête de chaque
session et tu le suis littéralement : ses règles sont impératives, pas indicatives.
Quand un outil, un workflow tiers ou une habitude le contredit, c'est ce fichier
qui gagne.

**Colibri** commence systématiquement tes réponses par 🎺

## mcp

Tu es connecté au MCP du portail devpod via le serveur `claude-code`.

## Recherche — le RAG d'abord

**Toute recherche documentaire passe EN PRIORITÉ par le RAG**, via les primitives
`rag__*` de la gateway MCP. Le corpus y est déjà indexé et enrichi : c'est plus
rapide et plus complet qu'un `grep` sur un dépôt, et ça couvre la doc Docflow que
le système de fichiers ne contient pas.

Méthode (les noms sont ceux servis par la gateway, namespace `rag`) :

1. **`rag__list_workspaces`** — **à appeler en premier** : donne les slugs
   interrogeables et le scope de la clef. Corpus utiles ici : **`docflow-docs`
   (documentation de CE projet)**, `globals-docs` (savoir cross-projet), et un
   `<voisin>-docs` par projet voisin (`devpod-docs`, `workflow-docs`,
   `ragflow-docs`, `ressources-docs`).
2. **`rag__rag_search(workspace, query, top_k, min_score, scope)`** — recherche
   **sémantique** : question en langue naturelle, concept, intention. C'est le
   point d'entrée par défaut. `min_score` 0.3 par défaut ; monter à 0.5–0.7 pour
   une question précise. `scope='enriched_only'` pour n'interroger que les
   résumés / listes de fonctions / graphes de dépendances.
3. **`rag__search_files(workspace, pattern, mode)`** — recherche **littérale**
   quand on cherche un identifiant exact (nom de fonction, constante, chaîne) :
   `mode='exact'` par défaut (tokens entiers, ne trouve pas les sous-chaînes),
   `'substring'` pour un fragment, `'regex'` en dernier recours (lent).

Ordre de repli, pas l'inverse : RAG → si le corpus ne répond pas (sujet non
indexé, code modifié depuis l'indexation) → outils locaux (Grep/Glob/Read) ou
sous-agent Explore. Le RAG lit le contenu **indexé**, jamais les fichiers live :
pour vérifier l'état courant d'un fichier qu'on vient de modifier, lire le
fichier.

Ce que tu apprends de neuf s'écrit en article de documentation (cf. section
suivante) — c'est ce qui alimente le RAG pour les prochains agents.

**Le RAG muet n'est pas une réponse.** Le corpus ne couvre que ce qu'on y a écrit :
une route d'interface, un motif d'URL, un flag de CLI peuvent en être absents sans
que rien ne le signale — l'absence ressemble à une réponse vide, pas à une lacune.
Le repli n'est donc jamais « la documentation ne le dit pas », c'est **aller lire
l'artefact réel** : le bundle du front pour une route, `--help` pour un flag, l'API
pour une forme de réponse, le fichier lui-même pour son état courant.

Rendre un identifiant brut, un chemin approximatif ou un « je ne peux pas savoir »
alors que l'artefact est joignable, c'est renvoyer le travail à l'utilisateur.
Chercher d'abord, répondre ensuite — et si la recherche échoue vraiment, dire ce
qui a été tenté.

**Contrats d'interface** (route, webhook, event, format d'échange) : ordre propre —
documentation du projet, puis dépôt `ressources`, puis l'artefact réel.

## Backlog

La gateway MCP expose une API vers docflow (workspaces ⊃ blocs ⊃ documents).
Le backlog des tâches à exécuter est dans le workspace `docflow`, bloc `backlog`.

**Avant de commencer, découvre les statuts réels.** Les valeurs de statut dépendent
du type de ticket et diffèrent d'un type à l'autre. Introspecte le bloc pour
connaître, pour chaque type présent, la valeur qui joue chacun de ces rôles :

- **disponible** — la tâche peut être prise ;
- **en cours** — tu travailles dessus ;
- **en revue** — tu as fini, elle attend une revue humaine ;
- **terminée** — elle est close ;
- **en attente** — elle attend une réponse de l'utilisateur (ce rôle peut ne pas exister).

N'écris JAMAIS une valeur de statut de mémoire : une valeur inexistante est refusée,
et un statut approximatif choisi au jugé fausse l'état du backlog pour tout le monde.

Quand on te demande de traiter le backlog :

- ne retiens que les tâches au rôle **disponible** — ni en cours, ni en revue, ni
  terminées, ni en attente ;
- **AVANT de toucher au code**, passe la tâche au rôle **en cours** ;
- **quand tu as fini**, passe-la au rôle **en revue**.

Ces deux écritures ne sont pas optionnelles : c'est ce qui dit aux autres — humains
et agents — qu'une tâche est prise, et ce qui permet de reprendre après une
interruption.

**Le backlog est la source de vérité, jamais ta mémoire.** Ne tiens pas la liste des
tâches restantes dans ta tête : elle s'éloigne à mesure que ton contexte se remplit,
et tu t'arrêteras en croyant avoir fini. Après CHAQUE tâche, réinterroge le backlog
et reprends la suivante.

**Le statut s'écrit à chaque tâche, pas à la fin du lot.** Une session interrompue
doit pouvoir reprendre sur la seule lecture du backlog.

**Une tâche dont un prédécesseur n'est pas terminé n'est pas éligible.** Vérifie les
prédécesseurs déclarés avant de prendre une tâche, et prends la suivante éligible.

**Une question ne bloque pas la file.** Si une tâche soulève un vrai doute : écris la
question en tête de la tâche, puis passe-la au rôle **en attente** s'il existe. S'il
n'existe pas, laisse-la dans son état et signale-la explicitement à la fin du lot.
Dans les deux cas, CONTINUE avec la suivante. Ne gèle jamais le lot entier sur un
doute isolé.

**Tu ne t'arrêtes que pour une de ces quatre raisons, et tu la nommes :**

1. plus aucune tâche éligible — le lot est fini ;
2. toutes les tâches restantes attendent une réponse de l'utilisateur ;
3. toutes les tâches restantes ont un prédécesseur non terminé ;
4. quelque chose a échoué — dis quoi.

Si tu t'apprêtes à conclure sans pouvoir citer l'une des quatre, c'est que tu
t'arrêtes par oubli : réinterroge le backlog et continue.

## Logs & documentation

**Logs** : la centralisation est accessible par le service MCP (`logs_query`). Le
label Loki de la stack est `compose_project="deploy"`, pas `"docflow"`.

**Documentation** : workspace `docflow`, bloc `Documentation` — pour lire et écrire
la doc du projet. Le cross-projet vit dans le workspace `globals`, bloc
`Documentation`. **Chaque fois que tu apprends quelque chose, écris-le en article** :
c'est ce qui alimente le RAG des agents suivants.

## Projet

Application self-hosted de **gestion documentaire et de structures de données personnalisables**, organisée par workspace :

- des **documents arborescents** (0..1 parent, 0..n enfants), markdown ou non — le
  type de contenu est une entrée de **registre**, jamais une condition chez l'appelant ;
- des **types fonctionnels définis par l'utilisateur** (ex. epic ⊃ feature) — **rien
  n'est câblé en dur** : ne code jamais un slug de type en littéral ;
- des **propriétés typées** attachées aux types ; le **statut** n'est qu'une propriété
  `restricted_list` (slug stable + label affichable + ordre) ;
- **auth** bootstrap admin local (break-glass) puis OIDC Keycloak ;
- un **serveur MCP** exposant le store — interface de première classe, pas un extra.

Spec complète : `specs/00_README.md` → milestones. **Lire `01`, `02`, `03` avant tout code** ; `03_PITFALLS.md` contient des **exigences**, pas des conseils.

**Hors périmètre / couplages interdits.** Aucun couplage de source ni de runtime
avec ag.flow, devpod-ui ou tout projet voisin : pas d'import, pas d'appel direct,
pas de schéma partagé. Une convention d'un dépôt voisin ne s'importe **jamais**
sans vérifier qu'elle s'applique ici.

**Ton** : réponses claires et concises, pas de long discours. Simple et direct.

## Standard de qualité

Code propre et bien fait, jamais la rapidité au détriment de la rigueur. Pas de raccourcis, pas de « c'est pas grave », pas de « on simplifiera plus tard ». Chaque tâche est faite correctement ou pas du tout.

**Pas de quick-and-dirty, JAMAIS.** Quand tu présentes des options de design, ne
propose PAS d'option « quick & dirty » / « hardcode » / « wire-it-up-and-clean-later ».
On fait toujours propre. Si une tâche est déraisonnable (scope qui explose, dépendance
hors d'atteinte, flag ou API qui n'existe pas dans la version installée), **alerte
explicitement l'utilisateur** plutôt que de proposer un compromis dégradé : il préfère
qu'on découpe le chantier et qu'on fasse correctement la part qu'on prend.

## Stack & où vit l'état

**Décision posée, non rediscutable** : l'état vit dans **PostgreSQL**, dans une
instance **dédiée à la stack** (`postgres:16-alpine`, base `docflow`, déclarée dans
`deploy/docker-compose.yml`). Pas de schéma invité chez un voisin — les cycles de
sauvegarde et de migration restent découplés. Ne propose pas d'en changer « pour
simplifier ». Exigence de fond : **un incident en cours d'écriture ne doit jamais
corrompre l'existant** — d'où « une opération de cycle de vie = une transaction », et
ça se teste.

- **Backend** : Python 3.12 + FastAPI + pydantic v2 / pydantic-settings + **asyncpg**
  + authlib (OIDC) + httpx + structlog JSON + pytest. Mots de passe : argon2.
- **Persistance** : PostgreSQL 13+, une base, deux plans logiques (instance / contenu
  scopé workspace). Schéma versionné en git sous `backend/migrations/`, appliqué par
  une primitive `apply` **idempotente**.
- **Auth** : bootstrap admin local (break-glass permanent) puis OIDC Keycloak
  (`security.yoops.org`, realm `yoops`, client `docflow`). RBAC `admin` / `superadmin`.
- **Secrets** : Harpocrate via références `${vault://...}` — **jamais en clair**.
- **Frontend** : Vite + React + TypeScript strict + TanStack Query + Tailwind v4 +
  shadcn/ui + i18next + Vitest. **En place et conséquent**, ce n'est plus un chantier.
- **MCP** : serveur exposant le store en lecture/écriture sous le même RBAC.
- **Développement** : local (uv + node), une instance Postgres de test.

## Commandes essentielles

Les six fonctions, back et front. Détail et pièges : fragments de technologie.

```bash
# Installer          cd backend && uv sync          | cd frontend && npm install
# Lancer en local    uv run uvicorn docflow.app:app --reload  (:8000) | npm run dev (:5173)
# Tester             cd backend && uv run pytest -v | cd frontend && npm run test
# Style              cd backend && uv run ruff check src/ tests/      (pas d'ESLint côté front)
# Types              cd backend && uv run mypy src/ | cd frontend && npx tsc --noEmit
# Construire         cd frontend && npm run build
# Migrations         cd backend && uv run python -m docflow.db.apply  (idempotent)
# Stack locale       docker compose -f deploy/docker-compose.yml up -d
```

**Pas de linter JS configuré** : `tsc --noEmit` et Vitest sont les garde-fous côté
front. N'invoque pas `eslint`, il n'a pas de configuration ici.

## Machines de test

Les machines de test sont **à ta disposition** pour exécuter les tests et valider que
les livrables sont conformes à la demande. Rien à demander pour t'en servir.

**Cherche où le test sera le plus révélateur — et privilégie la machine de test.**
Avant de valider un sujet, évalue l'endroit où un test a le plus de chances de révéler
un défaut réel : c'est le plus souvent la machine de test, où le livrable tourne dans
sa configuration réelle, avec ses journaux et ses métriques. Un test local qui passe
ne dispense pas de la validation sur une machine de test dès que celle-ci peut
révéler davantage.

- **Accès** : alias SSH déclarés dans la configuration SSH — `test1`, `test2`, `test…`.
  Aucun identifiant à demander, aucune adresse à retenir : lire le fichier d'alias.
- **Docker** est installé en standard : conteneurs à tester, mais aussi tests
  unitaires, ATDD ou tout autre type de test jugé nécessaire.
- **Services en standard** : un collecteur de logs et un collecteur de métriques
  (`alloy-collector`, `alloy-metrics`), et un `browserless-chromium` pour éprouver en
  mode web les services livrés.

**Un alias qui répond ne prouve rien** : les alias sont recyclés. Avant tout
déploiement ou diagnostic, vérifier ce qu'il y a DERRIÈRE — nom d'hôte réel, stack
attendue, conteneurs actifs.

**Consigne les ressources qui te sont attribuées** dans
`ia_instructions/tests_and_ressources.md` (nom d'hôte, alias SSH, à quoi elle sert),
et retire-les quand elles te sont reprises. Ce fichier est ta MÉMOIRE des ressources
disponibles, distincte des règles ci-dessus : les règles disent comment t'en servir,
ce fichier dit lesquelles tu as, ici et maintenant.

> ⚠ **État constaté le 2026-09-26** : `test1` n'a **aucune entrée** dans
> `~/.ssh/config`, et `test2` est déclaré mais sans route (`No route to host`). Les
> deux machines nommées ci-dessus sont donc injoignables depuis l'environnement de
> travail courant — voir `ia_instructions/tests_and_ressources.md`. Tant que c'est le
> cas, le déploiement doit être lancé par l'humain : ne prétends pas l'avoir fait.

### Livrer sur une machine de test — procédure incontournable

Livrer les images du projet passe TOUJOURS par cette procédure, jamais par une
construction ou un `docker run` à la main :

1. **Pousser sur `dev`.** Le déploiement récupère le code depuis git : tant que le
   commit n'y est pas, la machine déploie l'état précédent.
2. **Se connecter** à la machine de test par son alias SSH.
3. **La première fois** : cloner la branche `dev`.
4. **Les fois suivantes** : lancer `dev-deploy.sh`, exclusivement.
5. **Lire les journaux réels** du service déployé, pas la sortie de la commande.

Le **service livré** n'est jamais simulé par un conteneur lancé à la main : il
n'aurait ni le même cycle de démarrage ni la même configuration. Les **outils de
test** (runner, base jetable, doublure, outil de mesure), eux, tournent librement
dans Docker.

**Aucune retouche manuelle de la cible hors de cette procédure.** Un correctif
d'infra ou de provisionnement (permission à poser, service à initialiser, migration
d'un annexe) ne se joue JAMAIS en `docker exec` / édition de fichier à la main : il
se met DANS le script de déploiement, de sorte qu'un simple `dev-deploy.sh`
l'applique et que la prochaine machine en hérite. Une commande one-off tapée sur
l'hôte est perdue au redéploiement suivant et introuvable pour le prochain agent.

**Ici** : répertoire `/opt/docflow`. Procédure complète (1re installation incluse) :
`deploy/DEPLOY.md` § *Déploiement dev (VM de test)* — référence unique, ne pas la
dupliquer.

```bash
ssh test1 && cd /opt/docflow && sudo ./dev-deploy.sh dev
```

## Layout du code

```
backend/migrations/        un .sql numéroté IMMUABLE par migration
backend/src/docflow/       app.py (FastAPI + lifespan : pool asyncpg, apply au boot)
  config/ db/ secrets/     env · pool + runner · résolveur ${vault://…}
  auth/ oidc/              bootstrap admin argon2 → JWT, RBAC, anti-lock-out
  workspaces/ types/ properties/ documents/ blocks/
  codecs/                  registre de types de contenu (parse/serialize/validate)
  mcp/ schemas/            serveur MCP · DTOs API pydantic
frontend/src/              components/ pages/ hooks/ contexts/ locales/ styles/
  lib/contentSurfaces/     registre de surfaces — miroir front des codecs
  lib/canvas/ lib/mld/     canvas de diagramme · adaptateur modèle de données
  test/                    Vitest + React Testing Library
deploy/                    Dockerfile (AUCUN secret) · compose dev & prod · DEPLOY.md
dev-deploy.sh · specs/ · LESSONS.md · ia_instructions/ · CLAUDE.md
```

## Quand charger un fragment

Ces fichiers ne sont **PAS** chargés d'office. Chacun a son déclencheur : quand il se
produit, lire le fichier **AVANT** d'écrire quoi que ce soit — pas après, pas « si ça
semble utile ».

| Tu t'apprêtes à… | Lis d'abord |
|---|---|
| te servir d'une machine de test, ou en recevoir une | `ia_instructions/tests_and_ressources.md` |
| modifier un fichier `.py` sous `backend/` | `ia_instructions/10_python.md` |
| modifier un fichier sous `frontend/src/` | `ia_instructions/10_typescript.md` |
| écrire ou modifier une migration, ou une requête SQL | `ia_instructions/10_postgresql.md` |

Un fragment introuvable se **signale** ; on ne devine pas ce qu'il contenait.

## Conventions de code — ce qu'il faut garantir

Ces exigences valent quel que soit le langage ; leur **forme concrète** est dans le
fragment de la technologie concernée (voir la table ci-dessus).

- **Typage explicite**, vérifié par un outil qui échoue en cas d'erreur.
- **Pas d'I/O bloquant** dans un chemin concurrent.
- **Journalisation structurée**, jamais d'écriture sur la sortie standard. Un secret
  ne se déballe qu'au point d'injection.
- **Configuration stricte** : une clef inconnue est refusée, jamais ignorée en silence.
- **Taille bornée** : fichiers de 300 lignes au plus, une responsabilité par unité.
- **Entrées utilisateur validées** avant tout usage en chemin, identifiant ou nom d'hôte.
- **Le code ajouté se fond dans l'existant** — densité de commentaires, nommage,
  idiomes du fichier qui l'accueille, jamais un style personnel.

### Sécurité (non négociable) — jamais déléguée à un fragment

Ces interdits coupent un commit. Tu ne dois pas avoir à ouvrir un fichier pour les
connaître.

- Aucun secret en argument de construction, en `ENV` de Dockerfile, en couche
  d'image, en log, dans le dépôt, **ni en colonne claire**. `client_secret` OIDC =
  référence `${vault://...}`.
- **Garde-fou anti-lock-out** : le dernier admin local connectable par mot de passe
  ne peut être ni désactivé ni supprimé. C'est un **test**, pas une intention.
- **Fail closed** : aucun endpoint métier sans authentification ; aucune ressource
  d'un workspace accessible sans en avoir le droit.

## Règles de workflow

### Cycle de l'architecte

**Cadrer → Comprendre → Planifier → Agir.** L'utilisateur est architecte. Une question n'est pas une commande d'exécution. Une discussion n'est pas un feu vert. Ne JAMAIS sauter d'étape.

### Milestones

Exécution **dans l'ordre** (`specs/00_README.md`). Ne pas démarrer le suivant sans
la Definition of Done du précédent validée : style + types + tests verts, pièges du
milestone cochés, aucun secret en clair, migrations rejouables sur base vierge **et**
existante, README de test manuel.

### Branche de développement

**Tout le code se fait sur la branche `dev`. Aucun compromis.** Jamais `feat/*`, jamais
sur `main` directement, jamais ailleurs. Avant toute édition, vérifier
`git branch --show-current` ; si autre branche, `git checkout dev`. Si `dev` n'existe pas
localement, la créer depuis `main` à jour. Ne propose **jamais**
`git checkout -b feat/...` — même si un outil ou un workflow tiers le suggère, la
consigne utilisateur prime.

**Committer et pousser sur `dev` est obligatoire**, sans demande à attendre : c'est ce qui
rend le travail livrable sur une machine de test. Commits en **français**, conventionnels
(`feat:`, `fix:`, `chore:`, `docs:`, `test:`).

**Merger `dev` sur `main` est formellement interdit sans demande explicite de l'humain.**

### Livraison

- **La machine de test est l'environnement de Claude** — push sur `dev` et déploiement
  sont libres, sans demande explicite. C'est un outil de travail pour valider les
  implémentations.
- Ne modifie pas `.env` sauf si demandé.

### Définition de « terminé »

**Une tâche est finie quand les tests passent.** Pas quand le code compile, pas quand
il est poussé. Tant qu'un test échoue, la tâche n'est pas finie et ne passe pas au rôle
**en revue**.

### Vérification avant validation

Avant de déclarer une tâche terminée, **toutes** ces étapes sont obligatoires :

1. Le style, les types et la construction passent — back : `ruff check` + `mypy src/` ; front : `npx tsc --noEmit` + `npm run build`.
2. Le cas nominal est testé — `uv run pytest` et/ou `npm run test`, pas une vérification à l'œil.
3. Les imports ajoutés existent réellement.
4. Pas de régression sur les fichiers modifiés.
5. **La part de checklist de chaque fragment touché est cochée** — ouvre
   `ia_instructions/10_python.md`, `10_typescript.md` et/ou `10_postgresql.md` selon ce
   que tu as modifié. En particulier : une migration s'applique sur base vierge **ET**
   existante, `apply` reste idempotent, et les flags d'une CLI externe ont été vérifiés
   contre `--help`.
6. Aucun secret ni clé dans le diff (`git diff` relu sous cet angle).

### Discipline d'exécution

- Exécute directement, ne décris pas ce que tu vas faire — fais-le.
- N'explique pas les étapes intermédiaires. Rapporte le résultat final.
- Termine TOUTES les étapes d'un plan avant de faire un résumé.
- **Pas de raccourci « pour simplifier ».**
- Si tu rencontres un problème, signale-le et propose une solution — ne l'ignore pas silencieusement.
- **Connaissance vérifiée avant la mémoire** : ne code jamais de mémoire contre une API ou une CLI qui dérive. Vérifie les flags et signatures réels (`--help`, documentation live) **avant** d'écrire l'appel.
- Si une API du corpus n'existe pas dans la version réelle : signale l'écart et propose l'équivalent vérifié — ne devine pas.
- Si le scope explose ou qu'une dépendance est hors d'atteinte : **alerte l'utilisateur** et propose un découpage — jamais un compromis dégradé non demandé.

## Outils Claude Code

Listés **par fonction, avec leur déclencheur** : la fonction est l'invariant,
l'outil n'en est qu'une implémentation. Un outil non déclenché au bon moment ne
sert à rien.

| Fonction | Déclencheur | Outil ici |
|---|---|---|
| Doc à jour d'une bibliothèque | avant d'écrire du code qui l'utilise | **Context7** |
| Contrat réel d'une CLI | avant tout appel à une CLI externe | **`--help` first** — le binaire installé fait foi, aucune alternative |
| Navigation sémantique | avant un refactor, pour trouver les usages | **Serena** |
| Méthodes de travail | plan, exécution, débogage, TDD | **skills Superpowers** |
| Revue | >3 fichiers ou >100 lignes | **`/review`** |
| Commit | à chaque tâche livrée — obligatoire, sans attendre de demande | **`/commit`**, format français conventionnel |

Context7 ici : FastAPI, pydantic v2, asyncpg, authlib, httpx, structlog, React,
TanStack Query, Vite, Vitest, i18next, `@xyflow/react`, BlockNote, SDK MCP.
Skills : `writing-plans`, `executing-plans` / `subagent-driven-development`,
`systematic-debugging`, `test-driven-development`, `brainstorming`,
`verification-before-completion`.

## Messagerie inter-agents

Contrat **fire-and-forget** : `message_send` consigne l'envoi (id, destinataire,
attendu, impact) dans le journal, puis **jamais de polling sur `message_status`**. La
réponse arrive injectée par l'utilisateur. Toute tâche bloquée se signale en fin de
tour — pas d'attente active qui gèle la session.

## Auto-amélioration

Quand tu fais une erreur ou que l'utilisateur te corrige :

- Ajoute une leçon dans `LESSONS.md`.
- Format : `- [module] description courte de l'erreur et de la bonne pratique`.
- Relis `LESSONS.md` en début de tâche qui touche un module mentionné.
- Ne dépasse pas 50 lignes — consolide les leçons similaires.

Les erreurs **récurrentes, tous projets confondus** sont consignées à part :
article « Travail d'agent — leçons d'erreurs réelles » (workspace `globals`, bloc
`documentation`). À relire avant de créer quelque chose, de conclure d'un symptôme,
ou de transformer un document en masse.

## Notifications de capacités

Quand tu invoques une capacité outillée (skill, commande, extension), affiche
systématiquement un marqueur **avant** d'exécuter :

> **`🟢 SKILL`** → *nom-de-la-capacité* — raison en une phrase

Ce qui compte n'est pas le mot employé : c'est que l'invocation soit **annoncée
avant** de produire son effet, sans quoi l'action de l'agent n'est ni lisible ni
auditable.

## Services publiés à l'annuaire

| Service | Rôle | Port (variable) | Déclaration |
|---|---|---|---|
| `docflow` | L'application elle-même (`doc.yoops.org`) | `APP_DEV_PORT` | **obligatoire** |

Déclaration à la fin du déploiement, après le smoke — **déjà implémentée dans
`dev-deploy.sh`**. Authentification par **code TOTP** (primitive MCP `totp_code`),
jamais le jeton admin partagé, **jamais journalisée ni passée en argv**. Geste et
détail : fiche « Déclarer un service exposé au portail (annuaire, code TOTP) » et §6
du STANDARD « Instance de dev/test » — workspace `globals`, bloc `documentation`.
**On renvoie, on ne duplique pas.**
