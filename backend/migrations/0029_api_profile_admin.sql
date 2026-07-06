-- Migration 0029 : flag is_admin sur les profils API
-- Un profil admin contourne les vérifications de scope et accède aux primitives
-- structurelles : create_workspace, import_template, create_block.

ALTER TABLE api_profile ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT false;
