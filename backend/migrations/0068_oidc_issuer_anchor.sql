-- =====================================================================
-- 0068_oidc_issuer_anchor.sql — ancrage OIDC sur le couple (issuer, sub).
--
-- Avant : app_user.oidc_subject portait une unicité GLOBALE et la résolution se
-- faisait par ce seul champ. Or un `sub` n'est immuable que CHEZ UN émetteur
-- donné : deux `sub` identiques venant de deux émetteurs distincts entreraient
-- en collision, et une bascule d'émetteur perdait tout ancrage.
--
-- Repris de la référence a2a (migration 0010_oidc_identity_history) : on ancre
-- désormais sur (oidc_issuer, oidc_subject), et on conserve l'historique des
-- épinglages successifs pour l'audit et le retour en arrière d'une bascule.
--
-- Réconciliation additive : les comptes déjà épinglés reçoivent l'émetteur
-- courant (celui de oidc_config) et leur ligne d'historique ouverte.
-- =====================================================================

-- 1. Émetteur de l'épinglage courant (NULL pour les comptes locaux).
ALTER TABLE app_user ADD COLUMN oidc_issuer text;

-- 2. Backfill : les comptes déjà fédérés portaient le sub sans émetteur ; on
--    renseigne l'émetteur courant configuré (au plus une ligne oidc_config).
UPDATE app_user
SET oidc_issuer = (SELECT issuer FROM oidc_config LIMIT 1)
WHERE oidc_subject IS NOT NULL;

-- 3. L'unicité passe du sub seul au couple. Deux sub identiques chez deux
--    émetteurs distincts = deux comptes ; même émetteur + même sub = unique.
--    (Les comptes locaux ont les deux champs NULL → NULLs distincts en SQL,
--    plusieurs comptes locaux restent donc permis.)
ALTER TABLE app_user DROP CONSTRAINT IF EXISTS admin_user_oidc_subject_key;
ALTER TABLE app_user ADD CONSTRAINT app_user_oidc_pin_key UNIQUE (oidc_issuer, oidc_subject);

-- 4. Historique des couples (issuer, sub) d'un utilisateur. `app_user` porte
--    l'épinglage COURANT ; cette table mémorise les précédents (une seule ligne
--    ouverte, unlinked_at NULL, par utilisateur).
CREATE TABLE user_oidc_identity_history (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    issuer      TEXT        NOT NULL,
    sub         TEXT        NOT NULL,
    linked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- NULL tant que le couple est l'épinglage courant ; horodaté quand il est
    -- remplacé (bascule d'émetteur).
    unlinked_at TIMESTAMPTZ
);

CREATE INDEX idx_oidc_identity_history_user ON user_oidc_identity_history (user_id, linked_at DESC);
-- « Qui était cette personne chez l'ancien émetteur » : requête d'audit du jour
-- de bascule.
CREATE INDEX idx_oidc_identity_history_pin ON user_oidc_identity_history (issuer, sub);

-- 5. Réconciliation additive : ligne d'historique ouverte pour chaque compte
--    déjà épinglé, pour que l'historique soit complet dès maintenant.
INSERT INTO user_oidc_identity_history (user_id, issuer, sub, linked_at)
SELECT id, oidc_issuer, oidc_subject, created_at
FROM app_user
WHERE oidc_issuer IS NOT NULL AND oidc_subject IS NOT NULL;
