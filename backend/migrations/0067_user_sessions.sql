-- =====================================================================
-- 0067_user_sessions.sql — sessions serveur opaques et révocables.
--
-- Remplace le jeton HS256 signé par docflow (auth/jwt.py) pour l'IHM humaine.
-- Repris de l'implémentation de référence a2a (dépôt ag-flow/gateway,
-- migration 0011_user_sessions) : même modèle, adapté à app_user.
--
-- Le défaut le plus concret de l'ancien mécanisme n'était pas cryptographique :
-- la déconnexion ne déconnectait pas. Un jeton HS256 copié avant restait
-- valide jusqu'à son exp (8 h), et rien ne permettait de le révoquer. Ici toute
-- la décision vit en base — donc elle est révocable, immédiatement et réellement.
--
-- Divergence docflow assumée : contrairement à a2a, le secret jwt_secret n'est
-- PAS supprimé — il signe encore les liens d'artefacts, la preview et le backup
-- (usages HMAC distincts du jeton de session). Seul le jeton de session migre.
--
-- Même discipline que les clés API et les tickets d'upload : c'est l'EMPREINTE
-- du jeton (sha256) qui est stockée, jamais sa valeur. Une fuite de la base ne
-- rend aucune session.
-- =====================================================================

CREATE TABLE user_sessions (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    -- Empreinte sha256 du jeton porteur (le clair n'apparaît qu'une fois, à
    -- l'ouverture de session) — jamais stockée en clair.
    token_hash  TEXT        NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    -- Instant d'authentification RÉELLE, jamais rafraîchi : il porte le plafond
    -- absolu, indépendamment de l'activité.
    auth_time   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Glissé à chaque requête authentifiée : porte l'expiration par inactivité.
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Révoquer toutes les sessions d'un utilisateur (compromission) sans balayer
-- la table.
CREATE INDEX idx_user_sessions_user ON user_sessions (user_id);
CREATE INDEX idx_user_sessions_active ON user_sessions (user_id) WHERE revoked_at IS NULL;
