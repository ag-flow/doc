# docflow — Instructions Claude Code

> Nom de travail : **docflow** (à renommer une fois le produit nommé). Domaine de travail : `doc.yoops.org`.
> Projet **indépendant** d'ag.flow, devpod-ui (aucun couplage runtime ni de source).

> Généré depuis les standards globaux (docflow, workspace `globals`, bloc `documentation`).
> Génération : **2026-09-20**. Dernier `--update` : **2026-09-27**.
> Standards repris (titre — version du document au moment du report) : *Fichier
> d'instructions agent de projet* — **v42** · *Exposer un service interne derrière
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
>
> **Remise en forme du 2026-09-27 — ne pas défaire.** Le fichier atteignait 489 lignes
> pour un quota idéal de ~350. Sept blocs que l'agent ne mobilise qu'à un geste précis
> sont passés en **synthèse ici + texte intégral dans un fragment déclenché** : backlog,
> recherche, machines de test et livraison, tchat agents, commandes et layout, logs,
> outils. Chacun a sa ligne dans la table des déclencheurs. **Ne les remets pas en clair
> par réflexe** et **ne relève pas le plafond** : un fichier tronqué par l'agent perd des
> règles sans que personne ne le voie, un fichier remis en forme n'en perd aucune.

**Ce fichier prime sur ton comportement par défaut.** Tu le lis en tête de chaque
session et tu le suis littéralement : ses règles sont impératives, pas indicatives.
Quand un outil, un workflow tiers ou une habitude le contredit, c'est ce fichier
qui gagne.

**Colibri** commence systématiquement tes réponses par 🎺

## mcp

Tu es connecté au MCP du portail devpod via le serveur `claude-code`.

## Recherche — le RAG d'abord

**Toute recherche documentaire passe EN PRIORITÉ par le RAG** (primitives `rag__*` de
la gateway) : le corpus est indexé et enrichi, et il couvre la doc que le système de
fichiers ne contient pas. Ordre de repli, jamais l'inverse : `rag__list_workspaces`
d'abord, puis `rag__rag_search` (sémantique) ou `rag__search_files` (littéral) → et
seulement si le corpus ne répond pas, outils locaux.

**Le RAG muet n'est pas une réponse.** L'absence ressemble à une réponse vide, pas à
une lacune : le repli n'est jamais « la documentation ne le dit pas », c'est **aller
lire l'artefact réel** (`--help` pour un flag, l'API pour une forme de réponse, le
fichier pour son état courant). Rendre un chemin approximatif ou un « je ne peux pas
savoir » alors que l'artefact est joignable, c'est renvoyer le travail à l'utilisateur.

Détail des primitives, seuils et ordre pour les contrats d'interface :
`ia_instructions/recherche.md`.

## Backlog

Le backlog est dans le workspace `docflow`, bloc `backlog`, atteignable par la
gateway MCP.

**Les valeurs de statut sont définies PAR TYPE de ticket.** Introspecte le bloc pour
découvrir, par type, la valeur qui joue chaque rôle (disponible / en cours / en revue
/ terminée / en attente) — n'écris JAMAIS une valeur de mémoire, et ne filtre jamais
sur une liste de valeurs : `epic` n'a pas de `en_review`, et un filtre par valeurs
manque silencieusement des tickets ouverts.

**Prends une tâche au rôle disponible, passe-la « en cours » AVANT de toucher au code,
« en revue » quand tu as fini.** Le backlog est la source de vérité, jamais ta
mémoire : réinterroge-le après CHAQUE tâche. Une question ne gèle pas la file.

**Tu ne t'arrêtes que pour une raison que tu NOMMES** : plus aucune tâche éligible ·
toutes attendent une réponse · toutes ont un prédécesseur non terminé · quelque chose
a échoué. Sans l'une des quatre, tu t'arrêtes par oubli.

Règles intégrales (rôles, prédécesseurs, gestion des doutes) :
`ia_instructions/backlog.md`.

## Logs & documentation

**Logs** : primitive MCP `logs_query`. Le sélecteur de l'instance est
**`{host="docflow-dev", compose_service="app"}`** — `compose_project="deploy"` est
partagé avec le portail devpod et rendrait ses erreurs, pas les tiennes.

**Documentation** : workspace `docflow`, bloc `Documentation` (le cross-projet vit dans
`globals`). **Chaque fois que tu apprends quelque chose, écris-le en article** : c'est ce
qui alimente le RAG des agents suivants.

Pièges de labels et détail : `ia_instructions/logs.md`.

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

```bash
# Installer          cd backend && uv sync          | cd frontend && npm install
# Tester             cd backend && uv run pytest -v | cd frontend && npm run test
# Style / types      uv run ruff check src/ tests/ ; uv run mypy src/ | npx tsc -b
# Migrations         cd backend && uv run python -m docflow.db.apply  (idempotent)
```

`tsc --noEmit` ne vérifie **rien** ici (`"files": []` à la racine) : toujours `tsc -b`.
Pas d'ESLint configuré. Détail, lancement local et layout du code :
`ia_instructions/reperes_depot.md`.

## Machines de test et livraison

Les machines de test sont **à ta disposition**, rien à demander. **Privilégie-les** :
le livrable y tourne dans sa configuration réelle, avec ses journaux — un test local
qui passe ne dispense pas de la validation là-bas. **Un alias qui répond ne prouve
rien** : vérifie ce qu'il y a derrière avant tout déploiement.

**Livrer passe TOUJOURS par la procédure** : pousser sur `dev` → se connecter par
l'alias SSH → `dev-deploy.sh` → lire les journaux réels du service. Jamais un
`docker run` à la main pour simuler le service livré. **Aucune retouche manuelle de
la cible hors procédure** : un correctif d'infra se met DANS le script, sinon il est
perdu au redéploiement et introuvable pour le prochain agent.

**Consigne les ressources attribuées** dans `ia_instructions/tests_and_ressources.md`.

> ⚠ **État du 2026-09-26** : `test1` n'a aucune entrée dans `~/.ssh/config` et `test2`
> est sans route. Les deux machines sont injoignables d'ici : le déploiement doit être
> lancé par l'humain — ne prétends pas l'avoir fait.

Procédure complète, services standard et détail : `ia_instructions/livraison.md`
puis `deploy/DEPLOY.md` § *Déploiement dev (VM de test)*.

## Quand charger un fragment

Ces fichiers ne sont **PAS** chargés d'office. Chacun a son déclencheur : quand il se
produit, lire le fichier **AVANT** d'écrire quoi que ce soit — pas après, pas « si ça
semble utile ».

| Tu t'apprêtes à… | Lis d'abord |
|---|---|
| prendre, clore ou parcourir une tâche du backlog | `ia_instructions/backlog.md` |
| chercher une information documentaire ou un contrat d'interface | `ia_instructions/recherche.md` |
| committer, pousser, ou déployer sur une machine de test | `ia_instructions/livraison.md` |
| te servir d'une machine de test, ou en recevoir une | `ia_instructions/tests_and_ressources.md` |
| appeler un autre agent, ou te rendre appelable | `ia_instructions/tchat.md` |
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

1. Le style, les types et la construction passent — back : `ruff check` + `mypy src/` ; front : `npx tsc -b` + `npm run build`.
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

Chaque outil a son **déclencheur**, et un outil non déclenché au bon moment ne sert à
rien : **Context7** avant d'écrire du code qui utilise une bibliothèque · **`--help`
first** avant tout appel à une CLI externe, le binaire installé faisant foi ·
**Serena** avant un refactor · **skills Superpowers** pour les méthodes de travail ·
**`/review`** au-delà de 3 fichiers ou 100 lignes · **`/commit`** à chaque tâche livrée.

Table complète et périmètre de Context7 : `ia_instructions/outils.md`.

## Tchat agents

Coopération **fire-and-forget** : on envoie, on ne bloque pas, et **JAMAIS de polling**.
Une notification arrive par le marqueur `[TCHAT] nouveau message` injecté dans stdin.
Une conversation porte de la coordination et des **références** — l'information vit dans
docflow, pas dans le fil, qu'un TTL ramasse.

**Se rendre appelable en début de session** : `agent_register(session, command)` écrit le
registre que lit `tchat_list_agents` — sans lui, personne ne peut t'appeler même si ton
workspace tourne. Jamais `session_open` à la place : c'est un outil de spawn réservé au
portail.

> ⚠ **État du 2026-09-27** : `tchat_*` et `agent_register` **ne sont pas servis** par la
> gateway (vérifié via `gateway__list_backends`, pas seulement dans la liste cliente) —
> le tchat est un cadrage devpod non livré. En attendant, `message_send` reste le seul
> canal. Si ces outils paraissent absents une fois le cadrage livré, **ne conclus pas
> qu'ils n'existent pas** : la liste d'outils est figée à la connexion, reconnecte.

Détail, pièges et divergence assumée : `ia_instructions/tchat.md`.

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
