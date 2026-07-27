-- Invitation par lien à usage unique : docflow n'envoie pas d'e-mail, l'admin
-- copie le lien et le transmet lui-même. Le jeton n'est JAMAIS stocké en clair
-- (sha256) ; usage unique (used_at) ; expiration 7 jours.
CREATE TABLE IF NOT EXISTS user_invitation (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    token_hash  text NOT NULL UNIQUE,
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
