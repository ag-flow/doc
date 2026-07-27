-- Distingue les secrets HMAC des secrets génériques.
--
-- Le secret HMAC est SYMÉTRIQUE et PARTAGÉ avec le pair (workflow) : sa valeur
-- doit rester copiable par son propriétaire pour être renseignée côté workflow.
-- Les secrets génériques, eux, conservent l'invariant « valeur jamais révélée ».
-- La colonne kind sépare les deux politiques (l'endpoint de révélation est
-- réservé à kind = 'hmac', cf. vault/service.reveal_hmac_secret).
--
-- Additif : ADD COLUMN NOT NULL DEFAULT (valeur constante) — Postgres remplit
-- les lignes existantes sans réécriture lourde. Idempotent (IF NOT EXISTS).
ALTER TABLE user_secret
    ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'generic'
    CHECK (kind IN ('generic', 'hmac'));
