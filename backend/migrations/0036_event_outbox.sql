-- =====================================================================
-- 0036_event_outbox.sql — outbox transactionnel des events producteur workflow
--
-- docflow est producteur d'events pour le module workflow (cf. corpus
-- workflow, « Norme — Contrat producteur d'events »). Chaque mutation
-- métier écrit l'event dans cette table DANS SA PROPRE TRANSACTION : la
-- mutation et son event sont atomiques (aucun event fantôme, aucun event
-- perdu sur crash). Un worker de fond pousse ensuite les events non
-- envoyés vers l'ingestion workflow (enveloppe plate signée HMAC), avec
-- retry borné et backoff.
--
-- id  = _eventId de l'enveloppe : base de la déduplication côté workflow.
--       Réutilisé tel quel à chaque retry → idempotence.
-- payload = enveloppe plate complète (champs système _eventXxx + champs
--       métier à la racine), sérialisée telle qu'elle sera signée puis
--       postée. La signature n'y figure pas (calculée à l'envoi sur les
--       octets bruts).
-- workspace_technical_key = SET NULL à la suppression du workspace : le
--       payload est auto-porteur, un event de suppression doit pouvoir
--       partir même si le workspace disparaît ensuite.
-- =====================================================================

CREATE TABLE event_outbox (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_code      TEXT        NOT NULL
                    CHECK (event_code ~ '^[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*\.v[0-9]+$'),
    workspace_technical_key UUID
                    REFERENCES workspace(workspace_technical_key) ON DELETE SET NULL,
    payload         JSONB       NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,

    sent_at         TIMESTAMPTZ,
    attempts        INTEGER     NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Le worker balaie les events non envoyés prêts à (re)tenter, dans l'ordre
-- de création (index partiel : les events déjà envoyés sortent de l'index).
CREATE INDEX idx_event_outbox_pending
    ON event_outbox (next_attempt_at, created_at)
    WHERE sent_at IS NULL;
