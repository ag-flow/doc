-- Endpoint vault « propre » (STANDARD Harpocrate §3-§4) : l'endpoint ne contient
-- PLUS le token. Il gagne un propriétaire, une URL, une description, et RÉFÉRENCE
-- un secret local typé HARPOCRATE_API_KEY (qui, lui, porte le token). Le namespace
-- d'alias `name` reste GLOBAL (unique) : les références `${vault://name:/path}`
-- restent valides et résolubles sans session utilisateur.
--
-- Décisions (cadrage 2026-09-18) : endpoints par utilisateur (owner_ref) pour la
-- propriété de la clé et la gestion scoped-owner ; alias global pour la stabilité
-- des références et une résolution déterministe.

ALTER TABLE vault_wallet
    ADD COLUMN IF NOT EXISTS owner_ref UUID REFERENCES app_user(id) ON DELETE CASCADE;
ALTER TABLE vault_wallet ADD COLUMN IF NOT EXISTS url TEXT;
ALTER TABLE vault_wallet ADD COLUMN IF NOT EXISTS description TEXT;
-- NO ACTION (défaut) : la suppression d'un secret encore référencé est refusée
-- côté application (409) ; la suppression d'un utilisateur cascade endpoint ET
-- secret dans la même instruction (vérif en fin d'instruction, pas violée).
ALTER TABLE vault_wallet ADD COLUMN IF NOT EXISTS api_key_secret_ref UUID REFERENCES user_secret(id);

-- Backfill : pour chaque wallet legacy, créer un secret local HARPOCRATE_API_KEY
-- appartenant à l'admin d'amorçage. La valeur chiffrée est COPIÉE VERBATIM depuis
-- api_key_enc (même Fernet DOCFLOW_ENCRYPTION_KEY) — aucun plaintext ne transite.
DO $$
DECLARE
    boot uuid;
    w    RECORD;
    sid  uuid;
BEGIN
    IF EXISTS (SELECT 1 FROM vault_wallet WHERE api_key_secret_ref IS NULL) THEN
        SELECT id INTO boot FROM app_user WHERE is_admin ORDER BY created_at LIMIT 1;
        IF boot IS NULL THEN
            SELECT id INTO boot FROM app_user ORDER BY created_at LIMIT 1;
        END IF;
        IF boot IS NULL THEN
            RAISE EXCEPTION 'backfill vault_wallet : aucun app_user pour porter les coffres existants';
        END IF;
        FOR w IN SELECT id, name, api_key_enc FROM vault_wallet WHERE api_key_secret_ref IS NULL LOOP
            INSERT INTO user_secret (owner_ref, slug, label, value_enc, kind, secret_type)
            VALUES (boot, 'vault-key-' || w.name, 'Clé coffre ' || w.name,
                    w.api_key_enc, 'generic', 'HARPOCRATE_API_KEY')
            RETURNING id INTO sid;
            UPDATE vault_wallet SET api_key_secret_ref = sid, owner_ref = boot WHERE id = w.id;
        END LOOP;
    END IF;
END $$;

-- Le token vit désormais dans user_secret : la colonne inline disparaît.
ALTER TABLE vault_wallet DROP COLUMN IF EXISTS api_key_enc;

-- owner_ref et api_key_secret_ref sont obligatoires (backfill garanti ci-dessus ;
-- sur base vierge, aucune ligne à violer).
ALTER TABLE vault_wallet ALTER COLUMN owner_ref SET NOT NULL;
ALTER TABLE vault_wallet ALTER COLUMN api_key_secret_ref SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_vault_wallet_owner ON vault_wallet (owner_ref);
CREATE INDEX IF NOT EXISTS idx_vault_wallet_api_key_ref ON vault_wallet (api_key_secret_ref);
