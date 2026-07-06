-- =====================================================================
-- 0035_artifacts.sql — artefacts binaires (images) + références documents
--
-- artifact : contenu binaire stocké en base, scopé workspace, dédupliqué
--   par empreinte SHA-256 (UNIQUE par workspace). crc32 est conservé à
--   titre informatif ; l'identité de déduplication est sha256.
--
-- artifact_reference : dépendances document → artefact, reconstruites à
--   chaque enregistrement de document (miroir de document_reference).
--   Un artefact dont la dernière référence disparaît est supprimé
--   applicativement dans la même transaction ; un artefact jamais
--   référencé (collé dans un brouillon jamais enregistré) est purgé par
--   le worker après artifact_purge_after_hours.
-- =====================================================================

CREATE TABLE artifact (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_technical_key UUID NOT NULL
                    REFERENCES workspace(workspace_technical_key) ON DELETE CASCADE,

    -- Empreintes : sha256 = identité de dédup ; crc32 = informatif
    sha256          TEXT        NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    crc32           BIGINT      NOT NULL CHECK (crc32 >= 0 AND crc32 <= 4294967295),

    filename        TEXT        NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
    extension       TEXT        NOT NULL CHECK (extension ~ '^[a-z0-9]{1,16}$'),
    media_type      TEXT        NOT NULL CHECK (length(media_type) > 0),
    size_bytes      INTEGER     NOT NULL CHECK (size_bytes > 0),
    data            BYTEA       NOT NULL,

    created_by      UUID        REFERENCES app_user(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT artifact_ws_sha256_uix UNIQUE (workspace_technical_key, sha256)
);

CREATE TABLE artifact_reference (
    artifact_ref    UUID        NOT NULL
                    REFERENCES artifact(id) ON DELETE CASCADE,
    document_ref    UUID        NOT NULL
                    REFERENCES document(doc_technical_key) ON DELETE CASCADE,
    workspace_technical_key UUID NOT NULL
                    REFERENCES workspace(workspace_technical_key) ON DELETE CASCADE,

    PRIMARY KEY (artifact_ref, document_ref)
);

CREATE INDEX idx_artifact_reference_document ON artifact_reference(document_ref);
CREATE INDEX idx_artifact_ws ON artifact(workspace_technical_key);
