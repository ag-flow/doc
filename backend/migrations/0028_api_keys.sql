-- Migration 0028 : gestion des clés API (profils + scopes + clés)

CREATE TABLE api_profile (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_id, name)
);

CREATE TABLE api_profile_scope (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id     UUID NOT NULL REFERENCES api_profile(id) ON DELETE CASCADE,
    workspace_slug TEXT NOT NULL,
    block_slug     TEXT,
    read_only      BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE api_key (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id   UUID NOT NULL REFERENCES api_profile(id) ON DELETE CASCADE,
    owner_id     UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    label        TEXT NOT NULL,
    key_prefix   TEXT NOT NULL,
    key_hash     TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ
);

CREATE INDEX api_key_hash_active_idx ON api_key (key_hash) WHERE revoked_at IS NULL;

-- Unicité scope : (profile, workspace) pour les entrées workspace-entier (block_slug IS NULL)
--                 (profile, workspace, bloc) pour les entrées par bloc
CREATE UNIQUE INDEX api_profile_scope_ws_idx
    ON api_profile_scope (profile_id, workspace_slug)
    WHERE block_slug IS NULL;

CREATE UNIQUE INDEX api_profile_scope_ws_block_idx
    ON api_profile_scope (profile_id, workspace_slug, block_slug)
    WHERE block_slug IS NOT NULL;
