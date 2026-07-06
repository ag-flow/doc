-- Galerie distante : sources d'URLs enregistrées par l'administrateur.
-- La valeur GALLERY_URL de l'env apparaît en tête de liste côté API
-- (sans ligne DB) si elle n'est pas déjà présente.
CREATE TABLE IF NOT EXISTS gallery_source (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    label      text        NOT NULL,
    url        text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT gallery_source_url_uix UNIQUE (url)
);
