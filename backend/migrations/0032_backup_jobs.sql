-- =====================================================================
-- 0032_backup_jobs.sql — jobs de sauvegarde + historique d'exécution
--
-- backup_job : définition d'une tâche planifiée
--   strategy : 'db_dump' (pg_dump → remote_point SFTP/FTP)
--            | 'git_sync' (export documents → remote_point git)
--   schedule : expression cron (ex. '0 3 * * *') ou intervalle en secondes
--
-- backup_job_run : trace d'une exécution (succès / échec)
--   last_change_seq : curseur dans document_change_log (git_sync uniquement)
--   permet la reprise incrémentale au prochain run
-- =====================================================================

CREATE TABLE backup_job (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT        NOT NULL,
    label           TEXT        NOT NULL CHECK (length(label) > 0),
    strategy        TEXT        NOT NULL CHECK (strategy IN ('db_dump', 'git_sync')),
    enabled         BOOLEAN     NOT NULL DEFAULT true,

    -- Destination
    remote_point_id UUID        NOT NULL
                    REFERENCES remote_point(id) ON DELETE RESTRICT,

    -- Périmètre (git_sync uniquement — NULL = toute l'instance)
    workspace_technical_key UUID
                    REFERENCES workspace(workspace_technical_key) ON DELETE CASCADE,

    -- Planification
    schedule_cron   TEXT,                 -- ex : '0 3 * * *'  (mutuellement exclusif)
    schedule_every_seconds INTEGER        -- ex : 3600          (mutuellement exclusif)
                    CHECK (schedule_every_seconds > 0),

    -- Paramètres spécifiques git_sync
    git_base_path   TEXT,                 -- sous-répertoire dans le repo (NULL = racine)

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT backup_job_slug_uix UNIQUE (slug),
    CONSTRAINT backup_job_one_schedule
        CHECK (
            (schedule_cron IS NOT NULL)::int +
            (schedule_every_seconds IS NOT NULL)::int = 1
        )
);

CREATE TABLE backup_job_run (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID        NOT NULL
                    REFERENCES backup_job(id) ON DELETE CASCADE,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT        NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'success', 'error')),
    error_message   TEXT,                 -- NULL si succès

    -- Curseur incrémental pour git_sync
    last_change_seq BIGINT,               -- seq du dernier document_change_log traité

    -- Statistiques
    files_written   INTEGER,
    files_deleted   INTEGER,
    commit_sha      TEXT                  -- SHA du commit git (git_sync uniquement)
);

CREATE INDEX idx_backup_run_job      ON backup_job_run(job_id, started_at DESC);
CREATE INDEX idx_backup_run_status   ON backup_job_run(job_id, status) WHERE status = 'running';
