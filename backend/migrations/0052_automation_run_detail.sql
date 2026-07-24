-- =====================================================================
-- 0052_automation_run_detail.sql  (additif)
-- Détail des appels d'automate dans l'historique : corps envoyé (variables
-- résolues), URL, code HTTP, corps/message de réponse, eventCode déclencheur.
-- Colonnes nullables — les runs existants n'ont pas ces détails.
-- =====================================================================
alter table automation_run add column if not exists http_status  int;
alter table automation_run add column if not exists url          text;
alter table automation_run add column if not exists request_body text;
alter table automation_run add column if not exists response_body text;
alter table automation_run add column if not exists event_code   text;
