# 02 — Modèle de données

> Document de référence transversal. À lire après `01_ARCHITECTURE.md` et avant tout code métier.
> Le schéma canonique reste `0001_init.sql` ; ce document en explique le *pourquoi* et les invariants.

## Vue d'ensemble

Une seule base PostgreSQL, deux **plans logiques** :

```
┌─────────────────────────────────────────────────────────┐
│  Plan d'instance  (transverse — pas de workspace_key)   │
│                                                         │
│   admin_user          oidc_config                       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Plan de contenu  (chaque ligne porte workspace_key)    │
│                                                         │
│   workspace                                             │
│     └─ functional_type  (arbre)                         │
│          └─ properties_defs                             │
│               ├─ properties_constraints                 │
│               └─ properties_allowed_values  (statuts)   │
│     └─ data_block       (arbre)                         │
│     └─ document         (arbre)                         │
│          └─ properties_values                           │
└─────────────────────────────────────────────────────────┘
```

L'isolation entre workspaces est **applicative** : la colonne dénormalisée
`workspace_technical_key` est présente sur chaque table du plan de contenu.
Il n'y a pas de schema PostgreSQL séparé par workspace — le filtrage se fait
par `WHERE workspace_technical_key = $1` sur toutes les requêtes métier.

---

## Plan d'instance

### `admin_user`

Compte administrateur. Peut être :
- **local** : `password_hash` renseigné (argon2), `oidc_subject` null.
- **fédéré** : `oidc_subject` renseigné (rempli au 1er login Keycloak), `password_hash` peut rester non null (break-glass préservé).
- **hybride** : les deux renseignés — l'admin bootstrap qui a ensuite été lié à Keycloak.

| Colonne | Type | Rôle |
|---|---|---|
| `id` | uuid PK | clé technique |
| `email` | text UNIQUE NOT NULL | identité, clé fonctionnelle |
| `label` | text NOT NULL | nom affiché |
| `password_hash` | text | null = pas de login local |
| `oidc_subject` | text UNIQUE | `sub` Keycloak, rempli au 1er login fédéré |
| `is_superadmin` | boolean | droits étendus (gestion OIDC, autres admins) |
| `disabled` | boolean | compte désactivé (voir garde-fou) |

**Garde-fou anti-lock-out** (applicatif, non DDL) :
Le dernier `admin_user` avec `password_hash IS NOT NULL AND disabled = false`
ne peut être ni désactivé ni supprimé. Toute route qui écrit sur `admin_user`
vérifie cet invariant **avant** d'écrire. → test dédié obligatoire.

**Bootstrap** : à l'absence de toute ligne dans `admin_user`, un premier compte
est seedé depuis `ADMIN_EMAIL` / `ADMIN_PASSWORD` (env). Ce seed ne se produit
qu'une fois, et uniquement si la table est vide.

---

### `oidc_config`

Configuration du provider OIDC (Keycloak). Une seule ligne en pratique.

| Colonne | Type | Rôle |
|---|---|---|
| `id` | uuid PK | clé technique |
| `issuer` | text NOT NULL | URL du realm (ex. `https://security.yoops.org/realms/yoops`) |
| `client_id` | text NOT NULL | identifiant du client Keycloak |
| `client_secret_ref` | text NOT NULL | référence vault `${vault://...}` — **jamais en clair** |
| `enabled` | boolean | OIDC actif ou non |

`client_secret_ref` n'est résolu qu'au point d'usage (requête OIDC).
Il ne doit jamais apparaître dans un log, une réponse API, ou une représentation.

---

## Plan de contenu

### `workspace`

Unité d'isolation. Toutes les entités métier appartiennent à un workspace.

| Colonne | Type | Rôle |
|---|---|---|
| `workspace_technical_key` | uuid PK | clé de jointure dénormalisée dans toutes les tables enfants |
| `slug` | text UNIQUE NOT NULL | clé fonctionnelle stable (adressage externe) |
| `label` | text NOT NULL | nom affiché, renommable |
| `description` | text | optionnel |

Le `slug` est unique **globalement** (pas scoped au workspace — c'est le workspace lui-même).

---

### `functional_type`

Type fonctionnel défini par l'utilisateur (ex. Epic, Feature, Story, Bug).
Forme un **arbre** par `parent` auto-référent. Scoped workspace.

| Colonne | Type | Rôle |
|---|---|---|
| `id` | uuid PK | clé technique |
| `slug` | text NOT NULL | clé fonctionnelle — UNIQUE par workspace |
| `label` | text NOT NULL | affiché, renommable sans conséquence |
| `parent` | uuid FK → `functional_type(id)` RESTRICT | null = racine |
| `workspace_technical_key` | uuid FK → `workspace` CASCADE | scope |

**Contrainte DDL** : `UNIQUE(workspace_technical_key, slug)`.

**Invariants applicatifs** :
- Un enfant porte le même `workspace_technical_key` que son parent (vérifié à l'écriture).
- Déplacement d'une branche : le workspace est repropagé à tous les descendants.

Les types n'ont pas de sémantique câblée : Epic/Feature/Story sont des slugs
choisis par l'utilisateur. Le code ne connaît aucun slug en dur.

---

### `properties_defs`

Définition d'une propriété attachée à un `functional_type`. Chaque type peut
avoir N propriétés ; chaque propriété a un type parmi `text`, `int`, `restricted_list`.

| Colonne | Type | Rôle |
|---|---|---|
| `id` | uuid PK | clé technique |
| `slug` | text NOT NULL | clé fonctionnelle — UNIQUE par `functional_type_ref` |
| `label` | text NOT NULL | affiché |
| `functional_type_ref` | uuid FK → `functional_type(id)` CASCADE | porteur |
| `type` | text CHECK IN (`text`,`int`,`restricted_list`) | type de valeur |
| `default_value` | text | texte brut ; coercé et validé applicativement selon le type |
| `required` | boolean | absence de valeur = rejet à l'écriture |

**Contrainte DDL** : `UNIQUE(functional_type_ref, slug)`.

**Le statut n'est pas un concept spécial** : c'est une `properties_def` de type
`restricted_list` dont les `properties_allowed_values` définissent les états
possibles (voir ci-dessous). Aucune table `status` dédiée.

---

### `properties_constraints`

Contrainte de validation attachée à une `properties_def`.
Une seule contrainte par `(property_def_ref, kind)`.

| Colonne | Type | Rôle |
|---|---|---|
| `id` | uuid PK | clé technique |
| `property_def_ref` | uuid FK → `properties_defs(id)` CASCADE | porteur |
| `kind` | text NOT NULL | `min` \| `max` \| `min_length` \| `max_length` \| `pattern` |
| `value` | text NOT NULL | opérande (ex. `0`, `100`, `^[A-Z][A-Z0-9_]+$`) |
| `message` | text | message d'erreur lisible ; sinon message générique |

**Invariants applicatifs** :
- `kind=pattern` est réservé au type `text`. Refusé sur `int` ou `restricted_list`. → test de rejet.
- Les regex `pattern` sont évaluées **par l'application**, pas par PostgreSQL.
- `min` / `max` s'appliquent à `int` ; `min_length` / `max_length` à `text`.

---

### `properties_allowed_values`

Valeurs autorisées pour une `properties_def` de type `restricted_list`.
Sert aussi à modéliser les statuts (slug = clé stable, label = affiché, position = ordre du pipeline).

| Colonne | Type | Rôle |
|---|---|---|
| `id` | uuid PK | clé technique — **c'est cette clé qui est stockée dans `properties_values`** |
| `property_def_ref` | uuid FK → `properties_defs(id)` CASCADE | porteur |
| `slug` | text NOT NULL | clé fonctionnelle stable (ex. `ready_for_dev`) — le code pointe ici |
| `label` | text NOT NULL | affiché, renommable sans casser les valeurs stockées |
| `position` | integer | ordre de tri (pipeline de statuts) |
| `color` | text | code couleur optionnel (hex ou token) |

**Contrainte DDL** : `UNIQUE(property_def_ref, slug)`.

Renommer un label ne casse rien : les `properties_values` pointent l'`id` UUID,
pas le `slug` ni le `label`. Seul le `slug` est immuable une fois utilisé.

---

### `data_block`

Entité structurée typée (ex. une Epic concrète, une Feature). Forme un **arbre**
par `parent` auto-référent. Scoped workspace.

| Colonne | Type | Rôle |
|---|---|---|
| `id` | uuid PK | clé technique |
| `slug` | text NOT NULL | clé fonctionnelle — UNIQUE par workspace |
| `label` | text NOT NULL | affiché |
| `functional_type_ref` | uuid FK → `functional_type(id)` RESTRICT | type de ce bloc |
| `parent` | uuid FK → `data_block(id)` RESTRICT | null = racine |
| `workspace_technical_key` | uuid FK → `workspace` CASCADE | scope |

**Contrainte DDL** : `UNIQUE(workspace_technical_key, slug)`.

**Invariants applicatifs** (non exprimables en DDL) :
- Un enfant porte le même `workspace_technical_key` que son parent.
- Contrainte miroir (M6) : le `functional_type_ref` de l'enfant doit être un **fils direct** du `functional_type_ref` du parent ; la racine doit avoir un type racine. → test de rejet.
- Instanciation depuis template : préfixer les slugs (`projeta-…`) pour respecter l'unicité workspace.

---

### `document`

Page markdown arborescente. Peut porter un `functional_type_ref` (document typé,
porteur de `properties_values`). Forme un **arbre** par `parent`. Scoped workspace.

| Colonne | Type | Rôle |
|---|---|---|
| `doc_technical_key` | uuid PK | clé technique |
| `title` | text NOT NULL | titre affiché |
| `type` | text NOT NULL default `md` | type technique du document (`md` = markdown) |
| `functional_type_ref` | uuid FK → `functional_type(id)` RESTRICT | null = doc pur sans propriétés |
| `parent` | uuid FK → `document(doc_technical_key)` RESTRICT | null = racine |
| `contenu` | text | corps markdown |
| `workspace_technical_key` | uuid FK → `workspace` CASCADE | scope |

**Invariants applicatifs** :
- Un enfant porte le même `workspace_technical_key` que son parent.
- Les `properties_values` d'un document ne peuvent référencer que des `properties_defs`
  appartenant au `functional_type_ref` de ce document. → test de rejet.

---

### `properties_values`

Valeur d'une propriété sur un document. Une seule valeur par `(document_ref, property_def_ref)`.

| Colonne | Type | Rôle |
|---|---|---|
| `id` | uuid PK | clé technique |
| `document_ref` | uuid FK → `document(doc_technical_key)` CASCADE | porteur |
| `property_def_ref` | uuid FK → `properties_defs(id)` RESTRICT | définition |
| `value` | text | renseigné pour `text` / `int` ; null pour `restricted_list` |
| `allowed_value_ref` | uuid FK → `properties_allowed_values(id)` RESTRICT | renseigné pour `restricted_list` ; null sinon |
| `workspace_technical_key` | uuid FK → `workspace` CASCADE | dénormalisé — filtre à plat indexé |

**Contrainte DDL** :
- `UNIQUE(document_ref, property_def_ref)` — une seule valeur par propriété par document.
- `CHECK(NOT (value IS NOT NULL AND allowed_value_ref IS NOT NULL))` — jamais les deux.

**Invariants applicatifs** (le CHECK DDL interdit « les deux » ; l'appli interdit « le mauvais ») :
- Type `text` ou `int` → `value` renseigné, `allowed_value_ref` null.
- Type `restricted_list` → `allowed_value_ref` renseigné, `value` null.
- Propriété `required` sans valeur → rejet à l'écriture.
- Propriété absente → lecture retombe sur `default_value` de la `properties_def`.

**Pattern requête statut** : `WHERE workspace_technical_key = $1 AND allowed_value_ref = $2`
— couvert par les index `idx_pvalues_ws` + `idx_pvalues_allowed`.

---

## Récapitulatif des invariants applicatifs

Ces invariants ne sont pas exprimables en DDL. Chacun doit être **validé applicativement
et couvert par un test de rejet** (cf. `03_PITFALLS.md`).

| # | Invariant | Tables concernées | Test obligatoire |
|---|---|---|---|
| I-1 | Enfant = même workspace que le parent | `functional_type`, `data_block`, `document` | rejet si workspace différent |
| I-2 | `property_def` d'une valeur ∈ types du document | `properties_values`, `properties_defs` | rejet si def hors type |
| I-3 | `value` XOR `allowed_value_ref` selon le type | `properties_values` | rejet du mauvais champ |
| I-4 | Propriété `required` sans valeur → rejet | `properties_values`, `properties_defs` | rejet si absent |
| I-5 | Contrainte miroir `data_block` (M6) | `data_block`, `functional_type` | rejet si type incompatible |
| I-6 | `pattern` réservé au type `text` | `properties_constraints` | rejet si sur `int` |
| I-7 | Anti-lock-out : dernier admin local non désactivable | `admin_user` | rejet de la désactivation |
| I-8 | `client_secret_ref` jamais déballé en log/réponse | `oidc_config` | test de non-fuite |

---

## Clés fonctionnelles vs clés techniques

| Entité | Clé technique (code) | Clé fonctionnelle (humain) |
|---|---|---|
| workspace | `workspace_technical_key` UUID | `slug` |
| functional_type | `id` UUID | `slug` (scoped workspace) |
| data_block | `id` UUID | `slug` (scoped workspace) |
| document | `doc_technical_key` UUID | `title` (pas de slug sur document) |
| properties_def | `id` UUID | `slug` (scoped functional_type) |
| allowed_value | `id` UUID | `slug` (scoped property_def) |
| admin_user | `id` UUID | `email` |

**Règle** : le code, les templates et les intégrations pointent le **slug** (stable),
jamais le **label** (renommable). Les valeurs stockées dans `properties_values` pointent
l'`id` UUID de `properties_allowed_values`, pas le slug ni le label.

---

## Index

PostgreSQL n'indexe pas les FK automatiquement. Les index de `0001_init.sql`
couvrent :
- Toutes les FK vers `workspace_technical_key` (filtrage à plat par workspace).
- Toutes les FK parentes (`parent`) pour les traversées d'arbre.
- Les FK de `properties_*` (jointures fréquentes sur la chaîne def → contrainte/valeur autorisée/valeur).

Requête cœur — « tous les documents d'un workspace avec un statut donné » :
```sql
SELECT pv.document_ref
FROM   properties_values pv
WHERE  pv.workspace_technical_key = $1
  AND  pv.allowed_value_ref       = $2
```
Couvert par `idx_pvalues_ws` + `idx_pvalues_allowed` (deux index séparés,
PG choisit le plus sélectif ou un bitmap AND).
