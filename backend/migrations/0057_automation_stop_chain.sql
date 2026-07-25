-- =====================================================================
-- 0057_automation_stop_chain.sql  (additif)
-- Chaîne de responsabilité : un automate marqué stop_chain qui MATCHE un event
-- et dont l'appel RÉUSSIT « consomme » l'event — les automates de priorité
-- inférieure (position supérieure dans le workspace de l'event) ne le
-- traitent pas. document_event.consumed_by porte le consommateur ; la
-- comparaison de priorité se fait à l'évaluation (positions courantes).
-- =====================================================================
alter table automation add column if not exists stop_chain boolean not null default false;

alter table document_event add column if not exists consumed_by uuid
    references automation(id) on delete set null;
