-- =====================================================================
-- 0083_connect_flow.sql — état éphémère du parcours « Connecter à Harpocrate »
--
-- Entre le lancement (`start`) et le retour navigateur (`callback`), le
-- serveur doit retenir un `ConnectState` — code_verifier + clé privée EC
-- P-256 éphémère — SANS jamais l'exposer au navigateur. Aucune session
-- serveur existante ne porte de payload (`user_sessions` ne stocke qu'un
-- hash de jeton) : cette table est dédiée, à TTL court, sur le patron de
-- `upload_ticket` (migration 0065).
--
-- `state` (le paramètre OAuth-like renvoyé par le navigateur au callback)
-- n'est JAMAIS stocké en clair : seule son empreinte sha256 (`state_hash`)
-- sert de clé de lookup, comme pour `upload_id_hash` en 0065.
--
-- Les blobs `*_enc` sont déjà chiffrés par l'appelant (Fernet, module
-- `docflow.crypto`) : cette table ne fait QUE les persister opaques, elle
-- ne détient pas la clé de chiffrement.
--
-- Usage unique (`consumed_at`) + TTL (`expires_at`) + isolation stricte par
-- propriétaire (`owner_ref`) : une capture du `state` ne suffit pas à relire
-- l'état sans être aussi authentifié comme le même utilisateur.
-- =====================================================================

CREATE TABLE IF NOT EXISTS connect_flow (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Empreinte sha256 de `state` (hex) — le clair n'apparaît jamais en base.
    state_hash  TEXT        NOT NULL UNIQUE CHECK (state_hash ~ '^[0-9a-f]{64}$'),

    owner_ref   UUID        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,

    -- ConnectState chiffré au repos (contient la clé PRIVÉE EC éphémère).
    state_enc   TEXT        NOT NULL,
    -- Params de l'endpoint Harpocrate en attente ({name,url,description}) chiffrés.
    pending_enc TEXT        NOT NULL,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);

-- Balayage des lignes expirées par le nettoyage périodique (best-effort).
CREATE INDEX IF NOT EXISTS idx_connect_flow_expires ON connect_flow(expires_at);
