-- Stockage au choix par secret (STANDARD Harpocrate §5) : un secret est stocké
-- soit en LOCAL (valeur chiffrée en base), soit dans un endpoint VAULT (seul le
-- chemin est en base, la valeur vit dans Harpocrate). Aucun repli automatique.
--
-- value_enc devient nullable (les secrets vault n'ont pas de valeur locale). La
-- cohérence stockage/champs est exprimée en DDL (backstop) ET validée côté
-- application (messages 422). « exactly-one-of » : local ⇒ value_enc seule ;
-- vault ⇒ identifiant + chemin seuls.

ALTER TABLE user_secret
    ADD COLUMN IF NOT EXISTS storage_type TEXT NOT NULL DEFAULT 'local'
    CHECK (storage_type IN ('local', 'vault'));
ALTER TABLE user_secret ADD COLUMN IF NOT EXISTS vault_identifier TEXT;
ALTER TABLE user_secret ADD COLUMN IF NOT EXISTS vault_path TEXT;
ALTER TABLE user_secret ALTER COLUMN value_enc DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'user_secret_storage_shape'
    ) THEN
        ALTER TABLE user_secret ADD CONSTRAINT user_secret_storage_shape CHECK (
            (storage_type = 'local'
             AND value_enc IS NOT NULL
             AND vault_identifier IS NULL AND vault_path IS NULL)
            OR
            (storage_type = 'vault'
             AND value_enc IS NULL
             AND vault_identifier IS NOT NULL AND vault_path IS NOT NULL)
        );
    END IF;
END $$;
