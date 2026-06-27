-- =====================================================================
-- 0009_change_feed.sql — journal des changements de documents (spec 30_MCHG)
-- document_ref n'est PAS une FK : la ligne D doit survivre à la suppression
-- du document. La séquence garantit un curseur monotone stable.
-- =====================================================================

CREATE SEQUENCE document_change_log_seq START 1;

CREATE TABLE document_change_log (
    seq                     bigint      PRIMARY KEY DEFAULT nextval('document_change_log_seq'),
    workspace_technical_key uuid        NOT NULL
        REFERENCES workspace(workspace_technical_key) ON DELETE CASCADE,
    document_ref            uuid        NOT NULL,  -- pas de FK intentionnelle
    nature                  char(1)     NOT NULL CHECK (nature IN ('C', 'U', 'P', 'D')),
    occurred_at             timestamptz NOT NULL DEFAULT now()
);

-- Lecture paginée par curseur : WHERE workspace_technical_key = $1 AND seq > $2
CREATE INDEX idx_changelog_ws_seq
    ON document_change_log(workspace_technical_key, seq);
