-- =====================================================================
-- 0013_automation_tracking.sql  (additif — ne réécrit rien)
-- Suivi du journal par automate (curseur) + trace d'exécution (anti-rejeu).
-- La dédup est garantie par UNIQUE(automate, document, version) : un automate
-- ne s'exécute qu'une fois par VERSION d'un document -> 3 saves rapprochés
-- = 1 seul appel sur la version finale.
-- =====================================================================

create table automation_cursor (
    automation_ref uuid primary key references automation(id) on delete cascade,
    last_seq    bigint not null default 0,     -- dernier change_log.seq traité
    updated_at  timestamptz not null default now()
);

create table automation_run (
    id          uuid primary key default gen_random_uuid(),
    automation_ref uuid not null references automation(id) on delete cascade,
    document_ref uuid not null,                 -- PAS de FK : le document peut disparaître
    document_version integer not null,          -- la version traitée = clé de dédup
    change_log_seq bigint not null,             -- la ligne de journal déclencheuse
    status      text not null,                  -- ok | failed | skipped
    executed_at timestamptz not null default now(),
    unique (automation_ref, document_ref, document_version)   -- "déjà fait sur cette version"
);

create index idx_automation_run_automation on automation_run(automation_ref);
