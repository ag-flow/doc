-- =====================================================================
-- 0066_artifacts_mutable.sql — artefacts mutables (boucle agent lire→modifier→renvoyer)
--
-- Socle de l'epic « Maquettes d'écran dans docflow ». Ajoute la mutabilité aux
-- artefacts, de façon ADDITIVE (aucun changement de comportement sur l'existant) :
--
--   - `mutable`  : un artefact mutable garde son id à travers N écritures et est
--     EXCLU de la déduplication par sha256. L'identité ne peut pas être une
--     fonction du contenu quand le contenu change — sinon deux maquettes
--     initialisées avec le même squelette partageraient un id, et patcher l'une
--     modifierait l'autre (bug silencieux et grave).
--   - `revision` : compteur de la révision courante (la « tête »). Chaque
--     écriture crée la révision N+1.
--
-- La dédup sha256 devient un index unique PARTIEL `WHERE NOT mutable` :
-- strictement inchangée pour les artefacts immuables (tous les existants),
-- désactivée pour les mutables.
--
-- artifact_revision : historique complet des révisions d'un artefact mutable
-- (la tête est aussi sur `artifact.data` — tout le code de lecture existant est
-- inchangé). Consultable et purgeable (cf. fiche « Rétention des révisions »).
--
-- SÉCURITÉ : `.html` (text/html) n'est PAS ajouté au registre
-- artifact_media_type — le denylist anti-XSS (media_types.py) reste intact. Les
-- maquettes HTML passent par un canal applicatif dédié, réservé aux artefacts
-- mutables, jamais servi inline depuis l'origine docflow (cf. ADR « Frontière
-- HTML de maquette / denylist / origine de preview »).
-- =====================================================================

ALTER TABLE artifact
    ADD COLUMN mutable  BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1);

-- Dédup réservée aux immuables : index unique partiel de même portée que
-- l'ancienne contrainte totale pour les non-mutables ; aucune unicité pour les
-- mutables. (ON CONFLICT côté applicatif cible ce prédicat.)
ALTER TABLE artifact DROP CONSTRAINT artifact_ws_sha256_uix;
CREATE UNIQUE INDEX artifact_ws_sha256_uix
    ON artifact (workspace_technical_key, sha256)
    WHERE NOT mutable;

CREATE TABLE artifact_revision (
    artifact_ref UUID        NOT NULL REFERENCES artifact(id) ON DELETE CASCADE,
    revision     INTEGER     NOT NULL CHECK (revision >= 1),
    sha256       TEXT        NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes   INTEGER     NOT NULL CHECK (size_bytes > 0),
    data         BYTEA       NOT NULL,
    created_by   UUID        REFERENCES app_user(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (artifact_ref, revision)
);
