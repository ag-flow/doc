-- Table saved_view (spec 37 — MVIEW)
-- Deux index uniques partiels pour gérer le NULL sur owner_ref
-- (UNIQUE classique n'est pas NULL-safe sous PostgreSQL).
CREATE TABLE IF NOT EXISTS saved_view (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_technical_key uuid NOT NULL REFERENCES workspace(workspace_technical_key) ON DELETE CASCADE,
    bloc_ref                uuid,           -- NULL = tout le workspace
    owner_ref               uuid,           -- NULL = partagée ; UUID = privée
    slug                    text NOT NULL,
    label                   text NOT NULL,
    layout                  text NOT NULL CHECK (layout IN ('table', 'board')),
    filter                  jsonb NOT NULL DEFAULT '[]'::jsonb,
    sort                    jsonb NOT NULL DEFAULT '[]'::jsonb,
    group_by                text,           -- slug de propriété (obligatoire si board)
    columns                 jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

-- Unicité des vues partagées (owner_ref IS NULL) par workspace + slug
CREATE UNIQUE INDEX IF NOT EXISTS saved_view_shared_uix
    ON saved_view (workspace_technical_key, slug)
    WHERE owner_ref IS NULL;

-- Unicité des vues privées par workspace + owner + slug
CREATE UNIQUE INDEX IF NOT EXISTS saved_view_private_uix
    ON saved_view (workspace_technical_key, owner_ref, slug)
    WHERE owner_ref IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_saved_view_ws ON saved_view (workspace_technical_key);
