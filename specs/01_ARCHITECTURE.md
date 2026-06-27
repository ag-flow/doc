# 01 — Architecture & décisions

## Vue d'ensemble

Trois couches, faiblement couplées :

```
   ┌─────────────┐     ┌──────────────────────┐     ┌──────────────┐
   │  Front       │ →   │  Backend FastAPI      │ →   │  PostgreSQL  │
   │  (React)     │     │  (REST + MCP)         │     │  (1 base)    │
   └─────────────┘     └──────────────────────┘     └──────────────┘
                              │                          ▲
                              │ ${vault://...}           │ schéma versionné
                              ▼                          │ (migrations git)
                       ┌────────────┐              primitive `apply`
                       │ Harpocrate │
                       └────────────┘

   agflow-rag (RAG existant) ──(consomme l'API / le MCP)──► docflow
```

`docflow` est **un magasin** : stockage flexible + API + MCP. Le RAG (`agflow-rag`, déjà ~complet) n'est **pas** dans le périmètre ; il se branche en client via l'API REST ou le MCP. On ne réimplémente aucune brique RAG ici.

## Décision 1 — Postgres, et pas SQLite ni fichiers

**Contexte.** Le besoin est « stockage flexible » : types d'entités définis à l'exécution, propriétés typées, filtrage par statut/propriété.

**Options écartées.**
- *Fichiers plats (YAML/md)* : l'instinct everything-as-code, mais un filtrage « toutes les stories en Prêt-pour-dev » sur des fichiers décroche vite. Réservé au **schéma**, pas aux **données**.
- *Directus / headless CMS* : fait 90 % du besoin nativement, mais licence BSL/source-available — goulot qui peut se refermer (rachat, déplacement de seuil). Écarté pour rester maître à long terme.
- *SQLite* : envisagé (zéro serveur, inarrachable). Écarté car l'instance Postgres tourne déjà pour agflow-rag et offre une intégrité plus riche (FK enforced, CHECK, triggers si besoin).

**Décision.** PostgreSQL 13+. Licence PostgreSQL (vraiment open, aucun piège). **Divergence assumée vs devpod-ui** (qui interdit toute DB) : ici les propriétés typées et le filtrage l'exigent.

## Décision 2 — Une seule base, deux plans logiques

Pas deux fichiers, pas deux bases : **une base**, des tables regroupées en deux plans.

- **Plan d'instance** (transverse, sans `workspace_technical_key`) : `admin_user`, `oidc_config`.
- **Plan de contenu** (chaque ligne porte `workspace_technical_key`) : `workspace`, `functional_type`, `data_block`, `document`, `properties_*`.

Le cloisonnement entre workspaces est **applicatif**, via la colonne dénormalisée `workspace_technical_key` présente sur chaque ligne métier (filtrage « à plat » sans CTE récursif). Invariant : un enfant porte le même workspace que son parent.

## Décision 3 — Schéma-as-code + `apply` idempotent

Le réflexe everything-as-code est **préservé sur le schéma** (pas sur la donnée) :

- Le schéma vit en **migrations SQL numérotées** sous `backend/migrations/`, versionnées en git, diffables.
- La primitive **`apply`** est idempotente : elle applique les migrations manquantes dans l'ordre, en tenant une table `schema_migrations`. Rejouée, elle ne fait rien.
- **Réconciliation additive** : ajouter une propriété = `ADD COLUMN` nullable (instantané en PG moderne). Le renommage/suppression est rare → migration **explicite** et revue. On ne maintient pas de framework de migration destructive pour un événement qui survient trois fois par an. Invariant : **additif = automatique, destructif = explicite.**

## Décision 4 — Auth : bootstrap admin puis OIDC

On ne configure pas OIDC via OIDC. Pattern **break-glass** :

1. Au 1er boot, un admin local est seedé depuis l'env (`ADMIN_EMAIL`/`ADMIN_PASSWORD`) si `admin_user` est vide.
2. Il se connecte par mot de passe (argon2 → JWT/session), remplit `oidc_config`, l'active.
3. Les users passent ensuite par Keycloak (provisioning à la volée, `oidc_subject` rempli au 1er login fédéré).
4. **L'admin local reste connectable par mot de passe, toujours** — issue de secours si Keycloak tombe.

Le `client_secret` OIDC ne touche jamais la base en clair : colonne `client_secret_ref` = référence `${vault://...}` Harpocrate.

## Décision 5 — Statut = propriété, pas concept câblé

Un statut est une propriété de type `restricted_list` attachée à un `functional_type`, dont les valeurs autorisées (`properties_allowed_values`) sont les statuts : `slug` stable (`ready_for_dev`), `label` affichable (« Prêt pour dev »), `position` (= ordre du pipeline), `color` (extension). Renommer un label ne casse rien car les valeurs instanciées pointent l'**id** de l'allowed value, pas le label.

## Décision 6 — MCP de première classe

Le store est conçu pour être exposé par un serveur MCP (lecture/écriture sous le même RBAC, namespace par workspace). Ce n'est pas un bridge bolté après coup : c'est une cible de conception. Implémentation = milestone M9, mais les schémas DTO et la couche d'accès sont pensés pour ne pas avoir à être retordus à ce moment-là.

## Arbitrage de déploiement (à confirmer)

`docflow` dans **un schéma dédié de l'instance Postgres existante** (agflow-rag) — le plus économe, isolation logique suffisante — **ou** une **instance dédiée** (backups/montées de version découplés). Penchant : schéma dédié, sauf besoin explicite de découpler les cycles de backup. Le `0001_init.sql` prévoit un `CREATE SCHEMA` commenté pour ce cas.

## Hors périmètre

- Toute brique RAG / embeddings / pgvector → c'est `agflow-rag`, client de cette API.
- L'éditeur markdown riche, le temps réel collaboratif : non requis au démarrage.
