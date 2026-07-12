-- =====================================================================
-- 0037_backup_block_scope.sql
--
-- backup_job (git_sync) : périmètre affinable à un bloc + sa descendance,
-- en plus du périmètre workspace existant. NULL = comportement inchangé
-- (tout le workspace, ou toute l'instance si workspace_technical_key
-- est lui-même NULL).
--
-- remote_point : ajout de 'bitbucket' à la liste des providers git connus
-- (déjà github/gitlab/gitea/custom).
-- =====================================================================

ALTER TABLE backup_job
    ADD COLUMN data_block_ref UUID
        REFERENCES data_block(id) ON DELETE CASCADE;

CREATE INDEX idx_backup_job_block ON backup_job(data_block_ref)
    WHERE data_block_ref IS NOT NULL;

-- Cohérence bloc/workspace (un bloc appartient toujours à un workspace)
-- vérifiée applicativement à la création/mise à jour du job, pas en DDL :
-- pas de contrainte inter-tables simple sans trigger pour comparer
-- data_block.workspace_technical_key à backup_job.workspace_technical_key.

-- Le nom de la contrainte CHECK inline générée par Postgres en 0031 n'est pas
-- fixé explicitement dans ce corpus : on la retrouve dynamiquement par sa
-- définition plutôt que de parier sur le nom auto-généré (fragile si la
-- convention de nommage change entre versions de Postgres).
DO $$
DECLARE
    cname text;
BEGIN
    SELECT conname INTO cname
    FROM pg_constraint
    WHERE conrelid = 'remote_point'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%git_provider%';
    IF cname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE remote_point DROP CONSTRAINT %I', cname);
    END IF;
END $$;

ALTER TABLE remote_point ADD CONSTRAINT remote_point_git_provider_check
    CHECK (git_provider IN ('github', 'gitlab', 'gitea', 'bitbucket', 'custom'));
