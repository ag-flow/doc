-- 0044_event_outbox_dead_letter.sql
-- Robustesse de l'outbox d'events workflow.
--   #1 État terminal (dead-letter) : `failed_at` est posé quand les tentatives
--      sont épuisées (MAX_ATTEMPTS, côté worker). Une entrée dead-letter n'est
--      plus réclamée par le worker → fin de la boucle de retry infinie sur un
--      event rejeté en permanence (« poison »). La ligne reste en base pour
--      inspection.
--   #2 Purge des livrés : index partiel sur `sent_at` pour un DELETE ciblé des
--      events livrés plus vieux qu'une rétention.
ALTER TABLE event_outbox ADD COLUMN IF NOT EXISTS failed_at timestamptz;

CREATE INDEX IF NOT EXISTS event_outbox_sent_idx
    ON event_outbox (sent_at) WHERE sent_at IS NOT NULL;
