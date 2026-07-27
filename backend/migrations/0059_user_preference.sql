-- Préférences d'interface par utilisateur : petit key/value JSONB rattaché au
-- compte (et non au navigateur — le choix doit suivre l'utilisateur d'un poste
-- à l'autre). Première consommatrice : la sélection de colonnes de la liste des
-- documents, clé `doc-columns:<ws_slug>:<block_slug>`.
CREATE TABLE IF NOT EXISTS user_preference (
    user_id     uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    pref_key    text NOT NULL CHECK (char_length(pref_key) BETWEEN 1 AND 200),
    value       jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, pref_key)
);
