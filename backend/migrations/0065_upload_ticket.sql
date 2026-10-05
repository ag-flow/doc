-- =====================================================================
-- 0065_upload_ticket.sql — tickets d'upload d'artefact (upload en deux temps)
--
-- Voie d'écriture de binaire pour un agent qui détient déjà le fichier sur
-- son disque : les octets ne transitent JAMAIS par la conversation (contraire
-- de data_base64) ni par une URL déjà publiée (contraire de source_url).
--
--   1. create_upload  → un ticket (cette table), aucun artefact.
--   2. PUT upload_url  → les octets sont vérifiés (taille, extension au
--      registre, empreinte recalculée) puis rangés dans `data`.
--   3. create_artifact(upload_id) → l'artefact NAÎT complet ; le ticket est
--      consommé (usage unique) et son blob temporaire libéré (data = NULL).
--
-- `upload_id` est une capacité au porteur : aléatoire 128 bits, JAMAIS stocké
-- en clair (sha256), à usage unique, lié au workspace ET à l'utilisateur qui
-- l'a demandé, expirant sous un TTL court. Les tickets expirés (et leur blob)
-- sont nettoyés par le worker de purge.
-- =====================================================================

CREATE TABLE upload_ticket (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Empreinte sha256 du secret porteur (le clair n'apparaît qu'une fois, dans
    -- l'upload_url renvoyée par create_upload) — jamais stocké en clair.
    upload_id_hash          TEXT        NOT NULL UNIQUE CHECK (upload_id_hash ~ '^[0-9a-f]{64}$'),

    workspace_technical_key UUID        NOT NULL
                            REFERENCES workspace(workspace_technical_key) ON DELETE CASCADE,
    -- Utilisateur qui a demandé le ticket (porteur de la clé, jamais l'acteur
    -- OBO forgeable) : seul lui peut le consommer.
    requested_by            UUID        REFERENCES app_user(id) ON DELETE CASCADE,

    filename                TEXT        NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
    extension               TEXT        NOT NULL CHECK (extension ~ '^[a-z0-9]{1,16}$'),
    declared_size_bytes     INTEGER     NOT NULL CHECK (declared_size_bytes > 0),
    declared_sha256         TEXT        NOT NULL CHECK (declared_sha256 ~ '^[0-9a-f]{64}$'),

    -- Octets rangés à l'étape PUT (NULL avant, et de nouveau NULL après
    -- consommation pour libérer l'espace) ; jamais un artefact de 0 octet.
    data                    BYTEA,
    uploaded_at             TIMESTAMPTZ,
    consumed_at             TIMESTAMPTZ,

    expires_at              TIMESTAMPTZ NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Balayage des tickets expirés par le worker de purge.
CREATE INDEX idx_upload_ticket_expires ON upload_ticket(expires_at);
