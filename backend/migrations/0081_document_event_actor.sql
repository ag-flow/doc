-- =====================================================================
-- 0081 — `document_event` porte le GUID de l'acteur (fondation OBO sortant).
--
-- Un worker asynchrone doit pouvoir relayer l'identité de l'acteur qui a
-- déclenché la mutation vers un appel OBO sortant. Le journal `document_event`
-- est l'unique source que ce worker consulte (cf. outbox._record_document_event) :
-- l'acteur doit donc y être persisté au même titre que le reste du contexte de
-- corrélation (correlation_id/kind, origin, traceparent — migration 0070).
--
-- Nullable : une mutation sans acteur authentifié (automate interne, appel
-- système) n'a pas de GUID à relayer, et ce n'est pas une anomalie.
--
-- Rejouable : `add column if not exists` est sans effet si la colonne est là.
-- =====================================================================

alter table document_event add column if not exists actor_guid text;
