-- Secrets utilisateur : valeurs sensibles chiffrées appartenant à un utilisateur.
-- owner_ref → admin_user ; la valeur n'est JAMAIS retournée en clair via l'API.
CREATE TABLE IF NOT EXISTS user_secret (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_ref   UUID        NOT NULL REFERENCES admin_user(id) ON DELETE CASCADE,
    slug        TEXT        NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9_-]*$'),
    label       TEXT        NOT NULL CHECK (length(label) BETWEEN 1 AND 200),
    value_enc   TEXT        NOT NULL,   -- Fernet(DOCFLOW_ENCRYPTION_KEY)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_ref, slug)
);
CREATE INDEX IF NOT EXISTS idx_user_secret_owner ON user_secret (owner_ref);
