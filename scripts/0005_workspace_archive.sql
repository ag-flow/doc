-- =====================================================================
-- 0005_workspace_archive.sql  (additif — ne réécrit pas 0001)
-- Archivage non destructif d'un workspace : archived_at IS NULL = actif.
-- Le slug reste immuable et réservé même archivé (pas de réutilisation).
-- =====================================================================

alter table workspace add column archived_at timestamptz;

create index idx_workspace_active on workspace(archived_at);
-- liste des workspaces actifs = WHERE archived_at IS NULL
