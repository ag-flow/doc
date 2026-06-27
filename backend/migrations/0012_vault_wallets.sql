-- Wallets Harpocrate : nom (= api_name dans les références vault://) + clé API chiffrée
CREATE TABLE IF NOT EXISTS vault_wallet (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL UNIQUE
                              CHECK (name ~ '^[a-z0-9][a-z0-9_-]*$'),
    api_key_enc   TEXT        NOT NULL,   -- Fernet(DOCFLOW_ENCRYPTION_KEY)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
