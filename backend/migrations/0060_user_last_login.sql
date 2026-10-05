-- Dernière connexion réussie (login local ou callback OIDC). Additif ; NULL
-- pour un compte qui ne s'est jamais connecté.
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS last_login_at timestamptz;
