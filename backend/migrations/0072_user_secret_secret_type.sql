-- Typage FONCTIONNEL des secrets (`secret_type`), orthogonal à `kind`.
--
-- `kind` (0049) porte la POLITIQUE DE RÉVÉLATION (generic vs hmac). `secret_type`
-- classe le secret par USAGE fonctionnel : liste extensible en MAJUSCULES
-- (ex. GENERIC, HARPOCRATE_API_KEY). Il conditionne notamment l'endpoint vault
-- propre (T2) : une clé d'API de coffre est un secret local `HARPOCRATE_API_KEY`.
--
-- Additif : ADD COLUMN NOT NULL DEFAULT (constante) — Postgres remplit les lignes
-- existantes sans réécriture lourde. Idempotent (IF NOT EXISTS). Le CHECK impose
-- le format sans figer les valeurs (liste extensible côté applicatif).
ALTER TABLE user_secret
    ADD COLUMN IF NOT EXISTS secret_type TEXT NOT NULL DEFAULT 'GENERIC'
    CHECK (secret_type ~ '^[A-Z][A-Z0-9_]*$');
