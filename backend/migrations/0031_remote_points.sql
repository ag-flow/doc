-- =====================================================================
-- 0031_remote_points.sql — certificats SSH/TLS + points de connexion distants
--
-- remote_certificate : clés SSH (git/SFTP) et certificats TLS (FTPS)
--   identifiés par slug, clé privée chiffrée Fernet au repos
--
-- remote_point : connexion nommée vers un endpoint distant
--   types : ftp | ftps | sftp | git
--   auth  : password | pat | certificate
--   secret: stocké en local (Fernet) OU référence vault ${vault://...}
--
-- Les invariants de cohérence auth sont vérifiés applicativement ET en DDL.
-- =====================================================================

-- -------------------------------------------------------------------
-- Certificats : SSH (pour git/SFTP) et TLS (pour FTPS/mTLS)
-- -------------------------------------------------------------------
CREATE TABLE remote_certificate (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT        NOT NULL,
    label           TEXT        NOT NULL CHECK (length(label) > 0),
    cert_type       TEXT        NOT NULL CHECK (cert_type IN ('ssh_key', 'tls')),
    public_part     TEXT        NOT NULL, -- clé publique SSH ou cert PEM (non secret)
    private_enc     BYTEA       NOT NULL, -- clé privée chiffrée Fernet
    fingerprint     TEXT,                 -- SHA-256 fingerprint (affichage)
    expires_at      TIMESTAMPTZ,          -- NULL pour SSH, date d'expiration pour TLS
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT remote_certificate_slug_uix UNIQUE (slug)
);

-- -------------------------------------------------------------------
-- Points de connexion distants
-- -------------------------------------------------------------------
CREATE TABLE remote_point (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT        NOT NULL,
    label           TEXT        NOT NULL CHECK (length(label) > 0),
    point_type      TEXT        NOT NULL
                    CHECK (point_type IN ('ftp', 'ftps', 'sftp', 'git')),

    -- Connexion (commun à tous les types)
    host            TEXT        NOT NULL CHECK (length(host) > 0),
    port            INTEGER     CHECK (port BETWEEN 1 AND 65535),  -- NULL = défaut par type
    username        TEXT        NOT NULL CHECK (length(username) > 0),

    -- Git uniquement
    git_provider    TEXT        CHECK (git_provider IN ('github', 'gitlab', 'gitea', 'custom')),
    git_repo        TEXT,                 -- ex : 'org/monrepo'
    git_branch      TEXT        NOT NULL DEFAULT 'main',

    -- Authentification
    auth_type       TEXT        NOT NULL
                    CHECK (auth_type IN ('password', 'pat', 'certificate')),

    -- password / PAT : local (Fernet) OU vault
    auth_storage    TEXT        CHECK (auth_storage IN ('local', 'vault')),
    auth_secret_enc BYTEA,                -- chiffré Fernet ; non NULL si local
    auth_vault_ref  TEXT,                 -- ${vault://...} ; non NULL si vault

    -- certificate : référence par slug
    certificate_slug TEXT
                    REFERENCES remote_certificate(slug) ON DELETE RESTRICT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT remote_point_slug_uix UNIQUE (slug),

    -- Invariants auth — complétés par validation applicative (pydantic)
    CONSTRAINT rp_password_pat_needs_storage
        CHECK (auth_type = 'certificate' OR auth_storage IS NOT NULL),
    CONSTRAINT rp_local_needs_secret
        CHECK (auth_storage IS DISTINCT FROM 'local' OR auth_secret_enc IS NOT NULL),
    CONSTRAINT rp_vault_needs_ref
        CHECK (auth_storage IS DISTINCT FROM 'vault' OR auth_vault_ref IS NOT NULL),
    CONSTRAINT rp_certificate_needs_slug
        CHECK (auth_type IS DISTINCT FROM 'certificate' OR certificate_slug IS NOT NULL),

    -- Invariants git — complétés par validation applicative
    CONSTRAINT rp_git_needs_provider
        CHECK (point_type IS DISTINCT FROM 'git' OR git_provider IS NOT NULL),
    CONSTRAINT rp_git_needs_repo
        CHECK (point_type IS DISTINCT FROM 'git' OR git_repo IS NOT NULL)
);

CREATE INDEX idx_remote_point_type ON remote_point(point_type);
