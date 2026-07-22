-- =====================================================================
-- 0050_document_event_automation.sql  (additif + une contrainte revue)
-- Déclenchement des automates par les EVENTS du catalogue (les 6 codes
-- docflow.document.*), avec accès aux propriétés de l'event.
--
-- 1) document_event : journal DURABLE des events, écrit dans la transaction
--    de chaque mutation (via outbox.enqueue), INDÉPENDAMMENT de l'émission
--    workflow externe. C'est la source consommée par le worker d'automation.
-- 2) automation.event_codes : les eventCodes qui déclenchent l'automate
--    (remplace la sélection on_create/on_update, backfillée pour ne rien casser).
-- 3) automation_run : dédup par EVENT (event_seq) et non plus par version —
--    moved/retyped/propertyChanged peuvent porter la même version qu'un update.
-- =====================================================================

-- 1) Journal durable des events documentaires ------------------------------
create table if not exists document_event (
    seq         bigserial primary key,
    workspace_technical_key uuid
                references workspace(workspace_technical_key) on delete cascade,
    document_ref uuid,                         -- extrait de business.documentId ; pas de FK (le doc peut disparaître)
    event_code  text not null,
    business    jsonb not null default '{}'::jsonb,   -- propriétés métier de l'event (exposées en variables)
    occurred_at timestamptz not null default now()
);
create index if not exists idx_document_event_ws_seq
    on document_event (workspace_technical_key, seq);
create index if not exists idx_document_event_doc
    on document_event (document_ref, occurred_at);

-- 2) Sélection des events déclencheurs de l'automate -----------------------
alter table automation add column if not exists event_codes text[] not null default '{}';

-- Backfill : préserve le comportement des automates existants.
update automation
set event_codes =
        (case when on_create then array['docflow.document.created.v1'] else array[]::text[] end)
      || (case when on_update then array['docflow.document.updated.v1'] else array[]::text[] end)
where event_codes = '{}'::text[]
  and (on_create or on_update);

-- 3) Dédup par event -------------------------------------------------------
alter table automation_run add column if not exists event_seq bigint;
-- document_version devient facultatif (tous les events ne bumpent pas la version).
alter table automation_run alter column document_version drop not null;
-- L'ancienne dédup (automation, document, version) empêcherait deux events sur
-- la même version (ex. move + retype). On la remplace par (automation, event_seq).
alter table automation_run drop constraint if exists automation_run_automation_ref_document_ref_document_version_key;
create unique index if not exists uq_automation_run_event
    on automation_run (automation_ref, event_seq)
    where event_seq is not null;
