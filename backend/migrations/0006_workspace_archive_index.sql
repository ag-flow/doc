-- =====================================================================
-- 0006_workspace_archive_index.sql  (additif — ne réécrit pas 0002)
-- La colonne archived_at a été ajoutée par 0002_workspace_archived.
-- Ce fichier ajoute uniquement l'index pour les requêtes "actifs".
-- =====================================================================

create index if not exists idx_workspace_active on workspace(archived_at);
-- liste des workspaces actifs = WHERE archived_at IS NULL
