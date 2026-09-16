-- =====================================================================
-- 0070_event_correlation.sql  (additif)
-- STANDARD « Traçabilité du contexte » — le contexte de corrélation v1 est
-- porté dans l'enveloppe des events AVANT la mise en service (jamais une
-- reprise de données après coup). Deux tables d'outbox :
--   - document_event : journal durable consommé par les automates ;
--   - event_outbox   : bus producteur vers workflow.
-- Colonnes nullable (réconciliation additive) : les lignes antérieures
-- restent valides sans contexte ; les nouvelles le portent.
-- Le `correlation_id` est OPAQUE (uuid document ou id de fil) — jamais un
-- titre/slug. `traceparent` est le relais W3C du contexte de trace entrant.
-- =====================================================================

alter table document_event add column if not exists correlation_id   text;
alter table document_event add column if not exists correlation_kind text;
alter table document_event add column if not exists origin           text;
alter table document_event add column if not exists traceparent      text;

alter table event_outbox   add column if not exists correlation_id   text;
alter table event_outbox   add column if not exists correlation_kind text;
alter table event_outbox   add column if not exists origin           text;
alter table event_outbox   add column if not exists traceparent      text;

-- Retrouver tout le fil d'un document / d'une corrélation dans le journal.
create index if not exists idx_document_event_correlation
    on document_event (correlation_id);
create index if not exists idx_event_outbox_correlation
    on event_outbox (correlation_id);
