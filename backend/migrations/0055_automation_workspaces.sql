-- =====================================================================
-- 0055_automation_workspaces.sql  (additif)
-- Un automate peut couvrir PLUSIEURS workspaces : il est visible (et se
-- déclenche) dans tous les workspaces cochés. Table de liaison = source de
-- vérité de la portée ; automation.workspace_technical_key est conservée
-- (NOT NULL, « workspace d'origine », maintenue synchronisée = un élément de
-- l'ensemble). Un automate ne peut pas appartenir à aucun workspace —
-- invariant applicatif (422) + backfill ci-dessous.
-- =====================================================================
create table if not exists automation_workspace (
    automation_ref          uuid not null references automation(id) on delete cascade,
    workspace_technical_key uuid not null
        references workspace(workspace_technical_key) on delete cascade,
    primary key (automation_ref, workspace_technical_key)
);
create index if not exists idx_automation_workspace_ws
    on automation_workspace (workspace_technical_key);

-- Backfill : chaque automate existant couvre son workspace d'origine.
insert into automation_workspace (automation_ref, workspace_technical_key)
select id, workspace_technical_key from automation
on conflict do nothing;
