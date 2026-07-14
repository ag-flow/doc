-- =====================================================================
-- 0042_oidc_disable_local_login.sql
--
-- oidc_config.disable_local_login : mode OIDC-only piloté depuis la page
-- de configuration OIDC. Effectif UNIQUEMENT quand la config OIDC est
-- activée (enabled) : désactiver l'OIDC réactive donc automatiquement la
-- connexion locale. La variable d'environnement LOCAL_LOGIN_ENABLED
-- (absente par défaut) reste une surcharge break-glass fichier.
-- =====================================================================

ALTER TABLE oidc_config
    ADD COLUMN disable_local_login boolean NOT NULL DEFAULT false;
