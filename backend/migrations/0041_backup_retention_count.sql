-- =====================================================================
-- 0041_backup_retention_count.sql
--
-- backup_job.retention_count : nombre d'archives dump à conserver sur le
-- remote point pour ce job. Après chaque run réussi, les archives du job
-- au-delà de ce nombre (les plus anciennes, datées par leur nom) sont
-- supprimées, ainsi que leur fichier compagnon .key. NULL = tout garder.
-- =====================================================================

ALTER TABLE backup_job
    ADD COLUMN retention_count integer
        CHECK (retention_count IS NULL OR retention_count > 0);
