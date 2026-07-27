-- =====================================================================
-- 0058_user_identity.sql  (additif)
-- Champ identité OBO (contrat v6, GUID-only) : GUID que l'utilisateur pose
-- dans SON profil (libre ou généré), le MÊME que dans son profil portail.
-- x-portal-actor est mappé sur cette colonne — jamais sur le sub/login/email.
-- Nullable : sans GUID, l'utilisateur n'est pas propagé (fail-safe).
-- =====================================================================
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS identity TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS app_user_identity_uix
    ON app_user (identity) WHERE identity IS NOT NULL;
