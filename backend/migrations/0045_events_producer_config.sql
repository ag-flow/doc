-- =====================================================================
-- 0045_events_producer_config.sql — config runtime du producteur d'events
--
-- Table singleton (une seule ligne, id = true) pilotant l'émission d'events
-- workflow DEPUIS l'admin, sans redéploiement : activation, endpoint
-- d'ingestion, source, allowlist d'eventCodes relayés et référence du secret
-- HMAC. Le worker relit cette ligne à chaque tick (reconfiguration à chaud) ;
-- l'outbox l'applique via `reconcile`.
--
-- secret_ref = référence vault ${vault://wallet:/chemin} — JAMAIS le secret en
--       clair : il est résolu au point d'usage (worker / test-connection).
-- allowed_events = allowlist fermée (fail-closed) : vide = aucun event relayé.
--       Additive/idempotente (IF NOT EXISTS) pour rejouabilité sur base existante.
-- =====================================================================

CREATE TABLE IF NOT EXISTS events_producer_config (
    id             boolean     PRIMARY KEY DEFAULT true CHECK (id),  -- singleton
    enabled        boolean     NOT NULL DEFAULT false,
    ingestion_url  text,
    source_id      text,
    source_uri     text        NOT NULL DEFAULT 'docflow',   -- valeur du champ _source
    secret_ref     text,                                     -- référence vault ${vault://...}
    allowed_events text[]      NOT NULL DEFAULT '{}',         -- allowlist d'eventCodes (fail-closed)
    updated_at     timestamptz NOT NULL DEFAULT now()
);
