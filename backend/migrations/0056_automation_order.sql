-- =====================================================================
-- 0056_automation_order.sql  (additif)
-- Priorité d'évaluation des automates PAR WORKSPACE : la position vit sur la
-- table de liaison — le même automate peut avoir un ordre différent dans
-- chaque workspace couvert. Le worker évalue les automates dans cet ordre.
-- =====================================================================
alter table automation_workspace add column if not exists position integer not null default 0;

-- Backfill : ordre stable initial par workspace (date de création de l'automate).
with ranked as (
    select aw.automation_ref, aw.workspace_technical_key,
           row_number() over (
               partition by aw.workspace_technical_key
               order by a.created_at, a.id
           ) as rn
    from automation_workspace aw
    join automation a on a.id = aw.automation_ref
)
update automation_workspace aw
set position = ranked.rn
from ranked
where aw.automation_ref = ranked.automation_ref
  and aw.workspace_technical_key = ranked.workspace_technical_key
  and aw.position = 0;
