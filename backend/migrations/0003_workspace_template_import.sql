-- Trace des imports de template par workspace.
-- Garde-fou de version : (workspace, template) → version courante.
create table if not exists workspace_template_import (
    id                       uuid primary key default gen_random_uuid(),
    workspace_technical_key  uuid not null references workspace(workspace_technical_key) on delete cascade,
    template                 text not null,
    version                  integer not null,
    imported_at              timestamptz not null default now(),
    unique (workspace_technical_key, template)
);
