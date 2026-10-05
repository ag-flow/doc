-- Journal de livraison des webhooks : chaque envoi (réel ou en échec) laisse
-- une trace. Alimente « dernier envoi » et « échecs sur 24 h » de l'écran
-- Webhooks. Rétention applicative : purge des lignes de plus de 7 jours au fil
-- des écritures (pas de job dédié).
CREATE TABLE IF NOT EXISTS webhook_delivery (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_ref  uuid NOT NULL
        REFERENCES webhook_subscription(id) ON DELETE CASCADE,
    event        text NOT NULL,
    status_code  integer,          -- NULL = échec avant réponse HTTP
    error        text,
    duration_ms  integer NOT NULL DEFAULT 0,
    delivered_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_webhook_delivery_ref_at
    ON webhook_delivery(webhook_ref, delivered_at DESC);
