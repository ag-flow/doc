-- =====================================================================
-- 0040_backup_include_restore_env.sql
--
-- backup_job.include_restore_env : quand vrai, chaque run dump dépose
-- aussi `docflow_restore.env` (ENCRYPTION_KEY, JWT_SECRET, DATABASE_URL)
-- dans le répertoire de destination — le matériel nécessaire pour
-- restaurer un dump sur un serveur neuf. Désactivé par défaut : ce choix
-- (clé de chiffrement à côté des archives) appartient à l'opérateur.
-- =====================================================================

ALTER TABLE backup_job
    ADD COLUMN include_restore_env boolean NOT NULL DEFAULT false;
