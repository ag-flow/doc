# docflow — Guide des fonctionnalités

> Ce document décrit l'ensemble des fonctionnalités disponibles dans docflow, telles qu'implémentées. Il s'adresse aux administrateurs, aux utilisateurs avancés et aux intégrateurs.

---

## Sommaire

1. [Philosophie générale](#1-philosophie-générale)
2. [Authentification et accès](#2-authentification-et-accès)
3. [Workspaces](#3-workspaces)
4. [Types fonctionnels et hiérarchie](#4-types-fonctionnels-et-hiérarchie)
5. [Propriétés et statuts](#5-propriétés-et-statuts)
6. [Documents et arborescence](#6-documents-et-arborescence)
7. [Blocs de données](#7-blocs-de-données)
8. [Liens et références](#8-liens-et-références)
9. [Export Markdown / Obsidian](#9-export-markdown--obsidian)
10. [Vues sauvegardées](#10-vues-sauvegardées)
11. [Webhooks](#11-webhooks)
12. [Automates (push HTTP)](#12-automates-push-http)
13. [Coffre de secrets](#13-coffre-de-secrets)
14. [OIDC Keycloak](#14-oidc-keycloak)
15. [Templates de structure](#15-templates-de-structure)
16. [Templates de contenu](#16-templates-de-contenu)
17. [API publique](#17-api-publique)
18. [Serveur MCP](#18-serveur-mcp)
19. [Administration des utilisateurs](#19-administration-des-utilisateurs)

---

## 1. Philosophie générale

docflow est une application de **gestion documentaire personnalisable**. Ses principes fondateurs :

- **Aucun concept métier câblé en dur.** Il n'existe pas de table « statut », de champ « priorité » ou de type « tâche ». Tout est défini par l'utilisateur via des types fonctionnels et des propriétés.
- **Le slug est la clé fonctionnelle stable.** Les labels sont renommables à loisir ; le code, les templates et les intégrations pointent toujours le slug.
- **Une seule base PostgreSQL.** Deux plans logiques : instance (admin, OIDC) et contenu (scopé par workspace). Pas de multi-base, pas d'ORM lourd.
- **Fail closed.** Aucun endpoint métier sans authentification. Aucune ressource d'un workspace accessible sans en avoir le droit.
- **Non-lock-in.** L'export Markdown permet de récupérer ses données à tout moment, ouvrable directement comme vault Obsidian.

---

## 2. Authentification et accès

### 2.1 Wizard de premier démarrage

Au premier lancement, l'instance est vierge. Un écran de **wizard** guide la création du premier compte administrateur :

- `GET /api/setup/status` — l'application signale si l'instance est initialisée ou non.
- `POST /api/setup/init-admin` — crée le compte bootstrap (email + mot de passe). **Cette route n'est disponible qu'une seule fois**, tant que l'instance n'est pas initialisée.

### 2.2 Login local

Le compte bootstrap (et tout compte admin créé ensuite) se connecte par email + mot de passe :

- Mot de passe haché en **argon2** (résistant aux GPU).
- Retourne un **JWT** (Bearer token) utilisé dans toutes les requêtes API.
- `POST /api/auth/login`
- `GET /api/auth/me` — profil de l'utilisateur connecté.

### 2.3 OIDC Keycloak

En complément du login local, un administrateur peut configurer une authentification via **Keycloak** (ou tout provider OIDC compatible) :

- Configuration in-app : issuer, client_id, client_secret (stocké en référence vault).
- Callback OIDC disponible à `POST /api/auth/oidc/callback`.
- **Le compte bootstrap reste toujours disponible** (break-glass permanent) même si OIDC est configuré.

### 2.4 Garde-fou anti-lock-out

Le dernier administrateur local actif avec un mot de passe valide **ne peut pas être désactivé ni supprimé**. Cette règle est vérifiée applicativement à chaque modification d'utilisateur.

### 2.5 RBAC

Deux rôles : `admin` et `superadmin`. Les opérations sensibles (OIDC, vault, gestion des utilisateurs) requièrent `superadmin`.

---

## 3. Workspaces

Un workspace est la **partition racine** de tout le contenu. Tout (types, documents, blocs, vues, webhooks, automates) est scopé dans un workspace.

### Opérations disponibles

| Action | Endpoint |
|--------|----------|
| Lister | `GET /api/workspaces` |
| Créer | `POST /api/workspaces` |
| Lire | `GET /api/workspaces/{slug}` |
| Modifier (label, description) | `PATCH /api/workspaces/{slug}` |
| Archiver | `POST /api/workspaces/{slug}/archive` |
| Supprimer | `DELETE /api/workspaces/{slug}` |

Le **slug est immuable** une fois créé. Le label est renommable. L'archivage masque le workspace sans supprimer les données.

---

## 4. Types fonctionnels et hiérarchie

Un **type fonctionnel** (ou `functional_type`) est une catégorie de document définie par l'utilisateur. Exemples : `epic`, `feature`, `tâche`, `décision`, `personne`.

### Hiérarchie

Les types s'organisent en **arbre parent-enfant** illimité (`epic ⊃ feature ⊃ tâche`). Cette hiérarchie est ensuite utilisée comme **contrainte miroir** dans les blocs de données (voir §7).

### Opérations

| Action | Endpoint |
|--------|----------|
| Lister (plat) | `GET /api/workspaces/{ws}/types` |
| Lister (enrichi avec propriétés) | `GET /api/workspaces/{ws}/types/rich` |
| Créer | `POST /api/workspaces/{ws}/types` |
| Lire | `GET /api/workspaces/{ws}/types/{slug}` |
| Modifier (label, parent, template) | `PATCH /api/workspaces/{ws}/types/{slug}` |
| Supprimer | `DELETE /api/workspaces/{ws}/types/{slug}` |

---

## 5. Propriétés et statuts

Chaque type fonctionnel peut porter des **propriétés typées**, définies par l'utilisateur. Il n'existe pas de champ « statut » câblé : le statut est simplement une propriété de type `restricted_list`.

### Types de propriété disponibles

| Type | Description | Stockage | Validation |
|------|-------------|----------|------------|
| `text` | Texte libre | `text` | — |
| `int` | Entier | `text` (repr. numérique) | `int()` strict |
| `float` | Décimal | `text` (repr. `.`) | `float()` strict |
| `date` | Date ISO `YYYY-MM-DD` | `text` | `date.fromisoformat()` |
| `bool` | Booléen | `"true"` / `"false"` | littéral exact |
| `url` | URL absolue | `text` | scheme `http`/`https` + netloc |
| `restricted_list` | Liste de valeurs autorisées | `allowed_value_ref` | slug de l'allowed_value |
| `reference` | Pointeur vers un autre document | UUID (doc cible) | existence + type cible optionnel |

### Contraintes applicatives

Sur les types `int`, `float` et `date` : contraintes `min` / `max` avec message d'erreur personnalisé.
Sur `text` : contrainte `pattern` (expression régulière).

### Valeurs autorisées (`restricted_list`)

Pour une propriété de type `restricted_list`, on définit un ensemble de valeurs autorisées (`slug`, `label`, `position`, `color`). C'est ainsi que l'on crée un statut (ex. `to-do`, `in-progress`, `done`).

### Propriété `reference`

La propriété `reference` permet de pointer un autre document du même workspace. Elle peut être contrainte à un type fonctionnel cible (`target_functional_type_slug`) : si défini, seuls les documents de ce type sont acceptés. La validation se fait à l'écriture ; si la cible est supprimée ultérieurement, la référence devient orpheline (détection possible, pas de blocage).

### Valeurs versionnées

Chaque valeur de propriété est **versionnée** (optimistic concurrency control) : chaque mise à jour porte un `expected_version` ; en cas de conflit, l'API retourne la valeur actuelle (version + valeur) pour que le client puisse trancher.

### CRUD propriétés

```
/api/workspaces/{ws}/types/{type}/properties
/api/workspaces/{ws}/types/{type}/properties/{prop}/allowed-values
/api/workspaces/{ws}/types/{type}/properties/{prop}/constraints
```

---

## 6. Documents et arborescence

Un document est une **page markdown** appartenant à un workspace. Il peut avoir un parent (arborescence libre) et un type fonctionnel.

### Création

`POST /api/workspaces/{ws}/documents` — champs : `title`, `content` (markdown), `parent_id` (optionnel), `functional_type_slug` (optionnel), `bloc_slug` (rattachement à un bloc).

Si le type fonctionnel possède un **template de contenu** (§16) et que le corps est vide, le contenu est pré-rempli automatiquement.

### Édition avec versioning (OCC)

`PATCH /api/workspaces/{ws}/documents/{id}` — le corps contient `expected_version`. Si la version en base a changé entre-temps, l'API retourne `409 Conflict` avec la version actuelle pour résolution manuelle.

### Arbre et navigation

Les documents s'organisent en arbre par le champ `parent`. L'API retourne la liste plate ; l'arbre est reconstitué côté client. La recherche full-text (`GET /documents/search?q=`) permet de trouver un document par son titre (compatible avec le picker de liens).

### Valeurs de propriétés

`GET /documents/{id}/values` — lit toutes les valeurs de propriétés du document.
`PUT /documents/{id}/values/{prop_slug}` — pose ou met à jour une valeur (avec `expected_version` pour l'OCC).

### Exposition publique

`PATCH /documents/{id}/exposed` — rend un document accessible sans authentification via l'API publique.

### Journal des changements

Chaque modification (contenu, valeur de propriété) est tracée dans `document_change_log`. Ce journal est la source de vérité pour les automates (§12).

`GET /api/workspaces/{ws}/changes` — flux des dernières modifications.

---

## 7. Blocs de données

Un **bloc de données** (`data_block`) est un conteneur de documents à l'intérieur d'un workspace. Il structure la navigation (comme un « projet » ou une « base »). Chaque bloc peut déclarer un type fonctionnel racine — ce qui active la **contrainte miroir** : les enfants doivent être d'un sous-type du type racine.

Exemple : un bloc `projets-2026` de type racine `epic` n'accepte que des documents `epic`, `feature` ou `tâche` (sous-types d'`epic`).

### Opérations

```
GET  /api/workspaces/{ws}/blocks
POST /api/workspaces/{ws}/blocks
GET  /api/workspaces/{ws}/blocks/{bloc}
PATCH /api/workspaces/{ws}/blocks/{bloc}
DELETE /api/workspaces/{ws}/blocks/{bloc}
PATCH /api/workspaces/{ws}/blocks/{bloc}/exposed
GET  /api/workspaces/{ws}/blocks/{bloc}/allowed-types
POST /api/workspaces/{ws}/blocks/{bloc}/documents      ← crée un doc rattaché au bloc
GET  /api/workspaces/{ws}/blocks/{bloc}/documents      ← docs du bloc
GET  /api/workspaces/{ws}/blocks/{bloc}/values         ← valeurs batch de tous les docs
```

---

## 8. Liens et références

### 8.1 Liens de contenu (markdown)

Dans l'éditeur, un lien vers un autre document s'insère via `/link` : un picker recherche les documents par titre et insère `[Titre du doc](docflow://doc/{uuid})`. Au save, ces liens sont **extraits** et stockés dans `document_reference` (FK molle : la cible peut disparaître sans blocage).

### 8.2 Liens cassés

Un rapport des liens brisés est disponible :
- `GET /api/workspaces/{ws}/broken-links` — liste agrégée par bloc avec compteur.
- `GET /api/workspaces/{ws}/blocs/{bloc}/broken-links` — détail (document source, label du lien cassé).

### 8.3 Backlinks (références inverses)

Pour tout document, on peut obtenir la liste des documents qui **le citent** :

`GET /api/workspaces/{ws}/documents/{id}/backlinks`

Retourne : source_id, source_title, source_type, bloc, target_label. Le titre de la source est **live** (jointure en temps réel, pas un libellé figé).

Le panneau **« Référencé par »** dans l'éditeur affiche ces backlinks avec navigation vers la source.

### 8.4 Propriété `reference` (relation structurée)

Contrairement aux liens de contenu (souples, dans le markdown), la propriété `reference` est une **relation structurée** : portée par une propriété définie, validée à l'écriture, filtrable dans les vues sauvegardées, visible en backlink. C'est l'équivalent de la « relation to database » de Notion.

---

## 9. Export Markdown / Obsidian

`GET /api/workspaces/{ws}/export?scope=workspace`
`GET /api/workspaces/{ws}/export?scope=bloc&bloc={bloc_slug}`

Retourne une **archive ZIP** structurée en arbre de fichiers Markdown, ouvrable directement comme vault Obsidian ou graphe Logseq.

### Structure de l'archive

```
<workspace-slug>/
  <bloc-slug>/
    Doc-racine.md
    Doc-racine/
      Enfant-1.md
      Enfant-2.md
```

### Chaque fichier Markdown contient

Un **frontmatter YAML** avec :

```yaml
---
docflow_id: 4f3c…        # identité stable pour un futur round-trip
title: "Spec auth"
type: feature            # slug du type fonctionnel
statut: "Prêt pour dev"  # restricted_list → label affiché
echeance: 2026-09-15     # date
publie: false            # bool
charge: 3.5              # float
---
```

Suivi du **contenu markdown** du document, avec les liens `docflow://doc/{id}` vers des documents dans le périmètre d'export **réécrits en wikilinks** `[[Titre]]` (compatibles Obsidian). Les liens hors périmètre sont conservés tels quels.

**Aucune migration** — l'export est en lecture seule.

---

## 10. Vues sauvegardées

Une vue sauvegardée est une **requête nommée** sur les documents d'un workspace (ou d'un bloc) : filtres, tri, colonnes, layout. Elle peut être partagée (visible par tous) ou privée (visible par son créateur uniquement).

### Layouts

- **table** — liste tabulaire avec colonnes configurables.
- **board (kanban)** — colonnes groupées par une propriété `restricted_list` (statut).

### Filtres (conjonction AND)

Chaque prédicat porte sur un champ intégré ou une propriété :

| Champ | Opérateurs disponibles |
|-------|----------------------|
| `@title` | `contains`, `is_empty`, `not_empty` |
| `@type` | `is`, `is_not` |
| `@bloc` | `is`, `is_not` |
| Propriété `text` | `contains`, `is_empty`, `not_empty`, `is`, `is_not` |
| Propriété `int`/`float` | `=`, `!=`, `<`, `<=`, `>`, `>=`, `between`, `is_empty` |
| Propriété `date` | `before`, `after`, `on`, `between`, `is_empty` |
| Propriété `bool` | `is_true`, `is_false`, `is_empty` |
| Propriété `restricted_list` | `is`, `is_not`, `in`, `is_empty` |
| Propriété `reference` | `is`, `is_not`, `is_empty` |

Tous les prédicats sont **entièrement paramétrés** en base (jamais d'interpolation de chaîne dans le SQL).

### Opérations

```
GET  /api/workspaces/{ws}/views
POST /api/workspaces/{ws}/views
GET  /api/workspaces/{ws}/views/{slug}
PATCH /api/workspaces/{ws}/views/{slug}
DELETE /api/workspaces/{ws}/views/{slug}
GET  /api/workspaces/{ws}/views/{slug}/resolve   ← exécute la vue, retourne les docs
```

---

## 11. Webhooks

Les webhooks envoient une notification HTTP à une URL externe quand un document est créé, modifié ou supprimé.

### Événements

- `document.created`
- `document.updated`
- `document.deleted`

### Fonctionnalités

- Headers personnalisés (avec support des références vault pour les tokens d'authentification).
- Activation/désactivation sans suppression.
- Ping de test (`POST /webhooks/{id}/test`) : envoie un payload de test et retourne le status HTTP + erreur éventuelle.
- Livraison **best-effort** (pas de retry garanti). Pour des intégrations critiques, préférer les automates.

### Opérations

```
GET  /api/workspaces/{ws}/webhooks
POST /api/workspaces/{ws}/webhooks
GET  /api/workspaces/{ws}/webhooks/{id}
PATCH /api/workspaces/{ws}/webhooks/{id}
DELETE /api/workspaces/{ws}/webhooks/{id}
POST /api/workspaces/{ws}/webhooks/{id}/test
```

---

## 12. Automates (push HTTP)

Les automates déclenchent des appels HTTP vers des APIs externes quand un document change, avec un **curseur de journal** qui garantit qu'aucun changement n'est manqué (contrairement aux webhooks, qui sont best-effort).

### Principe

Un worker de fond (`worker_loop`) suit `document_change_log` via un curseur par automate. Quand un document trigger une condition (`on_create`, `on_update`), l'automate construit un appel HTTP avec un template de body et l'envoie.

### Contrats OpenAPI

Un automate peut être lié à un **contrat OpenAPI** importé dans l'application. Le contrat décrit les opérations disponibles (method, path, paramètres, schéma du body). L'utilisateur sélectionne une opération et configure le body template avec des variables (`{id_document}`, `{content}`, `{title}`…).

### Variables de substitution dans le body template

| Variable | Valeur |
|----------|--------|
| `{id_document}` | UUID du document |
| `{content}` | Contenu markdown du document |
| `{title}` | Titre du document |

### Cas d'usage principal

**Réindexation dans agflow-rag** : quand un document est modifié, l'automate appelle `POST /workspaces/{rag_ws}/index` pour maintenir l'index de recherche sémantique à jour.

### Fonctionnalités

- Délai de débounce (`delay_minutes`) : attend N minutes avant d'exécuter (absorbe les rafales d'éditions).
- Headers avec références vault (token d'auth jamais en clair).
- Historique des exécutions avec statut (`GET /automations/{id}/runs`).
- Rejeu d'une exécution (`POST /automations/{id}/runs/{run_id}/replay`).
- Déduplication garantie par la base : `UNIQUE(automation_ref, document_ref, document_version)`.

### Opérations

```
GET  /api/workspaces/{ws}/automations
POST /api/workspaces/{ws}/automations
GET  /api/workspaces/{ws}/automations/{id}
PATCH /api/workspaces/{ws}/automations/{id}
DELETE /api/workspaces/{ws}/automations/{id}
GET  /api/workspaces/{ws}/automations/{id}/runs
POST /api/workspaces/{ws}/automations/{id}/runs/{run_id}/replay
```

---

## 13. Coffre de secrets

Les secrets (tokens d'API, mots de passe, client_secret OIDC…) ne sont jamais stockés en clair. docflow supporte deux mécanismes :

### Wallets Harpocrate

Connexion à un serveur **Harpocrate** (gestionnaire de secrets E2E). Un wallet est référencé par un nom et une clé d'API. Les valeurs secrètes utilisent ensuite la syntaxe `${vault://nom-du-wallet:/chemin/du-secret}` — résolue à l'exécution, jamais logguée.

### Secrets locaux

Secrets stockés chiffrés dans la base docflow elle-même (chiffrement AES-GCM via `ENCRYPTION_KEY`). Utiles pour des secrets simples sans déploiement Harpocrate.

### Opérations

```
GET  /api/admin/vault/wallets
POST /api/admin/vault/wallets
DELETE /api/admin/vault/wallets/{id}
GET  /api/admin/secrets
POST /api/admin/secrets
DELETE /api/admin/secrets/{id}
```

---

## 14. OIDC Keycloak

docflow peut déléguer l'authentification à un provider OIDC (Keycloak, Auth0, etc.).

### Configuration

Via l'interface admin (superadmin requis) :
- **Issuer** : URL du provider OIDC.
- **Client ID** et **Client Secret** (stocké en référence vault, jamais en clair).
- Activation/désactivation sans perte de configuration.

Les utilisateurs OIDC sont **provisionnés à la volée** à la première connexion. Le compte bootstrap local reste toujours accessible (break-glass).

### Opérations

```
GET /api/admin/oidc         ← lecture config (superadmin)
PUT /api/admin/oidc         ← création/modification
GET /api/auth/oidc/config   ← config publique pour le frontend
GET /api/auth/methods       ← méthodes disponibles (local, oidc, needs_setup)
POST /api/auth/oidc/callback ← callback OAuth2
```

---

## 15. Templates de structure

Un template de structure définit un ensemble de types fonctionnels, de propriétés et de blocs qui peuvent être importés dans un workspace en une seule opération. C'est l'équivalent d'un « starter kit » de workspace.

Les templates sont des fichiers YAML stockés dans l'application. L'import est **idempotent** : relancer un import sur un workspace déjà initialisé ne crée pas de doublons.

### Opérations

```
GET  /api/templates                 ← liste avec metadata
GET  /api/templates/{slug}/yaml     ← contenu YAML
PUT  /api/templates/{slug}/yaml     ← sauvegarde
DELETE /api/templates/{slug}
POST /api/templates                 ← import dans un workspace
```

---

## 16. Templates de contenu

Un **template de contenu** est un squelette markdown associé à un type fonctionnel. Quand un document est créé avec ce type et que le corps est vide, le contenu est **pré-rempli automatiquement** avec le template.

### Variables disponibles

| Variable | Valeur insérée |
|----------|---------------|
| `{{title}}` | Titre du document |
| `{{date}}` | Date du jour (ISO `YYYY-MM-DD`) |

Les variables inconnues sont conservées telles quelles (pas d'erreur). Le template est un **point de départ**, pas une contrainte : l'utilisateur édite librement ensuite. Modifier le template d'un type **n'altère pas** les documents déjà créés.

### Configuration

Via l'interface `TypesAdmin` → onglet du type → champ "Modèle de contenu".

API : `PATCH /api/workspaces/{ws}/types/{slug}` avec `{ "content_template": "# {{title}}\n\n## Contexte\n" }`.

---

## 17. API publique

Certains documents peuvent être exposés publiquement (sans authentification) en activant le flag `exposed`. L'API publique est accessible sous le préfixe `/pub`.

```
GET /pub/documents/{doc_id}          ← document exposé
GET /pub/documents/{doc_id}/children ← enfants exposés
```

Seuls les documents avec `exposed = true` sont accessibles. Les documents non exposés retournent 404.

---

## 18. Serveur MCP

docflow expose un **serveur MCP** (Model Context Protocol) permettant à des agents IA (Claude, etc.) d'interagir avec le store en lecture et en écriture sous le même RBAC.

Connexion SSE : `GET /api/mcp/sse`
Messages : `POST /api/mcp/messages`

Le serveur est configuré au démarrage de l'application et partage le pool de connexions PostgreSQL.

---

## 19. Administration des utilisateurs

Les comptes admin locaux sont gérés via l'interface d'administration.

### Opérations

```
GET  /api/admin/users
POST /api/admin/users
GET  /api/admin/users/{id}
PATCH /api/admin/users/{id}        ← label, email, disabled, is_superadmin
POST /api/admin/users/{id}/password ← reset du mot de passe
DELETE /api/admin/users/{id}
```

### Garde-fous

- Le dernier admin local actif avec mot de passe **ne peut pas être supprimé ni désactivé** (anti-lock-out vérifié applicativement à chaque opération).
- Un utilisateur ne peut pas se supprimer lui-même.
- La promotion/révocation `superadmin` est réservée aux superadmins.

---

## Annexe — Contrats OpenAPI

Les contrats OpenAPI permettent de décrire des APIs externes et de les référencer dans les automates.

```
GET  /api/admin/contracts
POST /api/admin/contracts
GET  /api/admin/contracts/{id}       ← avec opérations parsées et body_skeleton
POST /api/admin/contracts/{id}/refresh ← recharge depuis source_url
PATCH /api/admin/contracts/{id}
DELETE /api/admin/contracts/{id}
```

---

## Annexe — Réactions et commentaires

Les documents supportent des réactions (like/dislike) et des commentaires.

- `GET  /api/workspaces/{ws}/documents/{id}/reactions`
- `POST /api/workspaces/{ws}/documents/{id}/reactions`
- `GET  /api/workspaces/{ws}/documents/{id}/comments`
- `POST /api/workspaces/{ws}/documents/{id}/comments`
- Les commentaires supportent eux-mêmes des réactions.

---

*Document généré depuis les specs et l'implémentation. Dernière mise à jour : 2026-06-28.*
