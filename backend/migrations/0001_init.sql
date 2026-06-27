-- =====================================================================
-- Lot 1 — Schéma initial (PostgreSQL 13+)
-- Gestion documentaire & structures de données personnalisables par workspace.
--
-- Conventions :
--   * clés techniques = UUID (gen_random_uuid, natif PG13+ ; sinon pgcrypto)
--   * clés fonctionnelles = slug
--   * réconciliation additive : ADD COLUMN reste cheap (nullable = instantané)
--   * destructif = explicite : composition -> CASCADE, référence -> RESTRICT
--
-- Isolation : pour cohabiter avec agflow-rag dans la même instance,
-- décommenter la création de schéma dédié ci-dessous.
-- =====================================================================

-- create schema if not exists docflow;
-- set search_path to docflow, public;

-- ---------------------------------------------------------------------
-- Plan d'instance (transverse — aucun workspace_technical_key)
-- ---------------------------------------------------------------------

create table admin_user (
    id              uuid primary key default gen_random_uuid(),
    email           text not null unique,
    label           text not null,
    password_hash   text,                       -- null si user OIDC pur
    oidc_subject    text unique,                -- 'sub' Keycloak, rempli au 1er login fédéré
    is_superadmin   boolean not null default false,
    disabled        boolean not null default false,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
-- Garde-fou anti-lock-out (le dernier admin local connectable par mot de passe
-- ne doit jamais être désactivable) : tenu applicativement, pas en DDL.
-- Bootstrap admin : seedé au 1er boot depuis l'env (ADMIN_EMAIL/ADMIN_PASSWORD),
-- une seule fois si la table est vide. Pas dans la migration.

create table oidc_config (
    id                  uuid primary key default gen_random_uuid(),
    issuer              text not null,           -- ex. https://security.yoops.org/realms/yoops
    client_id           text not null,
    client_secret_ref   text not null,           -- référence vault Harpocrate ${vault://...}, jamais en clair
    enabled             boolean not null default false,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Plan de contenu
-- ---------------------------------------------------------------------

create table workspace (
    workspace_technical_key uuid primary key default gen_random_uuid(),
    slug        text not null unique,            -- racine : unique global (adressage)
    label       text not null,
    description text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create table functional_type (
    id          uuid primary key default gen_random_uuid(),
    slug        text not null,
    label       text not null,
    parent      uuid references functional_type(id) on delete restrict,
    workspace_technical_key uuid not null
                references workspace(workspace_technical_key) on delete cascade,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (workspace_technical_key, slug)
);

create table data_block (
    id          uuid primary key default gen_random_uuid(),
    slug        text not null,
    label       text not null,
    functional_type_ref uuid not null references functional_type(id) on delete restrict,
    parent      uuid references data_block(id) on delete restrict,
    workspace_technical_key uuid not null
                references workspace(workspace_technical_key) on delete cascade,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (workspace_technical_key, slug)
);

create table document (
    doc_technical_key uuid primary key default gen_random_uuid(),
    title       text not null,
    type        text not null default 'md',      -- type technique du doc
    functional_type_ref uuid references functional_type(id) on delete restrict,
    parent      uuid references document(doc_technical_key) on delete restrict,
    contenu     text,
    workspace_technical_key uuid not null
                references workspace(workspace_technical_key) on delete cascade,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Propriétés : définition (defs) -> contraintes / valeurs autorisées -> valeurs
-- ---------------------------------------------------------------------

create table properties_defs (
    id          uuid primary key default gen_random_uuid(),
    slug        text not null,
    label       text not null,
    functional_type_ref uuid not null references functional_type(id) on delete cascade,
    type        text not null check (type in ('text','int','restricted_list')),
    default_value text,                          -- texte ; coercé/validé applicativement
    required    boolean not null default false,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (functional_type_ref, slug)
);

create table properties_constraints (
    id          uuid primary key default gen_random_uuid(),
    property_def_ref uuid not null references properties_defs(id) on delete cascade,
    kind        text not null,                   -- min | max | min_length | max_length | pattern ...
    value       text not null,                   -- opérande (ex. 0, 100, ^[A-Z][A-Z0-9_]+$)
    message     text,                            -- message lisible (nullable) ; sinon message générique
    created_at  timestamptz not null default now(),
    unique (property_def_ref, kind)
);

create table properties_allowed_values (
    id          uuid primary key default gen_random_uuid(),
    property_def_ref uuid not null references properties_defs(id) on delete cascade,
    slug        text not null,                   -- valeur stable pointée par le code (ex. ready_for_dev)
    label       text not null,                   -- affichage renommable (ex. Prêt pour dev)
    position    integer not null default 0,      -- ordre = pipeline
    color       text,                            -- EXTENSION (statut coloré) ; nullable
    created_at  timestamptz not null default now(),
    unique (property_def_ref, slug)
);

create table properties_values (
    id          uuid primary key default gen_random_uuid(),
    document_ref uuid not null references document(doc_technical_key) on delete cascade,
    property_def_ref uuid not null references properties_defs(id) on delete restrict,
    value       text,                            -- text / int
    allowed_value_ref uuid references properties_allowed_values(id) on delete restrict, -- restricted_list
    workspace_technical_key uuid not null
                references workspace(workspace_technical_key) on delete cascade,  -- dénormalisé (filtre à plat)
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (document_ref, property_def_ref),
    check (not (value is not null and allowed_value_ref is not null))   -- jamais les deux
);

-- ---------------------------------------------------------------------
-- Index (PG n'indexe pas les FK automatiquement ; + colonnes de filtrage à plat)
-- ---------------------------------------------------------------------

create index idx_functional_type_ws     on functional_type(workspace_technical_key);
create index idx_functional_type_parent on functional_type(parent);
create index idx_data_block_ws          on data_block(workspace_technical_key);
create index idx_data_block_parent      on data_block(parent);
create index idx_data_block_ftype       on data_block(functional_type_ref);
create index idx_document_ws            on document(workspace_technical_key);
create index idx_document_parent        on document(parent);
create index idx_document_ftype         on document(functional_type_ref);
create index idx_pdefs_ftype            on properties_defs(functional_type_ref);
create index idx_pconstraints_def       on properties_constraints(property_def_ref);
create index idx_pallowed_def           on properties_allowed_values(property_def_ref);
create index idx_pvalues_doc            on properties_values(document_ref);
create index idx_pvalues_def            on properties_values(property_def_ref);
create index idx_pvalues_allowed        on properties_values(allowed_value_ref);
create index idx_pvalues_ws             on properties_values(workspace_technical_key);
-- idx_pvalues_ws + allowed_value_ref = la requête "tous les docs en statut X
-- d'un workspace" reste un WHERE plat indexé.
