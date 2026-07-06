-- Ajout d'un username unique sur admin_user pour le wizard de premier démarrage.
-- Colonne nullable pour la réconciliation additive (enregistrements existants conservés).
ALTER TABLE admin_user ADD COLUMN IF NOT EXISTS username TEXT;

-- Remplir username à partir de l'email pour les comptes existants.
UPDATE admin_user SET username = split_part(email, '@', 1) WHERE username IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS admin_user_username_uix ON admin_user (username);
