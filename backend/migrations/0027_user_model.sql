-- Conversion admin_user → app_user avec is_admin, validated, source
-- Les FKs existantes (reactions, user_secret) suivent automatiquement le renommage.

ALTER TABLE admin_user RENAME TO app_user;
ALTER TABLE app_user RENAME COLUMN is_superadmin TO is_admin;

ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS validated BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS source    TEXT    NOT NULL DEFAULT 'local'
        CHECK (source IN ('local', 'oidc'));

-- Les utilisateurs existants (bootstrap admin) sont déjà validés.
UPDATE app_user SET validated = true;

-- Index sur username déjà créé en 0021 — on le recrée avec le bon nom de table.
DROP INDEX IF EXISTS admin_user_username_uix;
CREATE UNIQUE INDEX IF NOT EXISTS app_user_username_uix ON app_user (username);

-- Propriétaire du workspace.
ALTER TABLE workspace
    ADD COLUMN IF NOT EXISTS owner_id UUID REFERENCES app_user(id) ON DELETE SET NULL;
