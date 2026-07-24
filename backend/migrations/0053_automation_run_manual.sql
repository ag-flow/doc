-- =====================================================================
-- 0053_automation_run_manual.sql  (additif)
-- Distingue les runs déclenchés MANUELLEMENT (« jouer l'event ») des runs
-- automatiques du worker. Les runs manuels sont historisés avec event_seq NULL
-- (aucune dédup, ne bloquent pas le traitement auto de l'event).
-- =====================================================================
alter table automation_run add column if not exists manual boolean not null default false;
