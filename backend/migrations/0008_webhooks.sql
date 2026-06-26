-- =====================================================================
-- 0008_webhooks.sql — abonnements webhook (spec 29_MWH)
-- Scopé workspace. Headers chiffrés Fernet au repos.
-- =====================================================================

CREATE TABLE webhook_subscription (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_technical_key uuid        NOT NULL
        REFERENCES workspace(workspace_technical_key) ON DELETE CASCADE,
    label                   text        NOT NULL CHECK (length(label) > 0),
    url                     text        NOT NULL CHECK (length(url) > 0),
    headers_encrypted       bytea,                          -- JSON Fernet, nullable
    events                  text[]      NOT NULL DEFAULT '{}',
    active                  boolean     NOT NULL DEFAULT true,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

-- Index partiel : seuls les abonnements actifs sont cherchés à l'émission
CREATE INDEX idx_wh_workspace_active
    ON webhook_subscription(workspace_technical_key)
    WHERE active;
