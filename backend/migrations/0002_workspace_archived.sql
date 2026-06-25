-- 0002_workspace_archived.sql
-- Ajout colonne archivage workspace (additive, nullable → pas de valeur par défaut requise)
ALTER TABLE workspace ADD COLUMN IF NOT EXISTS archived_at timestamptz;
