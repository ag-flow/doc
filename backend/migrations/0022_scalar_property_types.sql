-- Élargissement du CHECK de properties_defs.type pour accepter les types
-- scalaires : date, bool, url, float.
-- Le CHECK inline posé dans 0001 est auto-nommé properties_defs_type_check.
-- Additif : plus permissif → aucune ligne existante n'est rejetée.
-- Idempotent : on DROP avant ADD (les deux opérations sont dans une
-- transaction DDL).

DO $$
BEGIN
    -- Tenter de supprimer la contrainte existante si elle est encore là
    -- (idempotence : sur une base vierge le premier apply, sur une base
    --  existante les re-jeux suivants).
    ALTER TABLE properties_defs DROP CONSTRAINT IF EXISTS properties_defs_type_check;
    ALTER TABLE properties_defs ADD CONSTRAINT properties_defs_type_check
        CHECK (type IN ('text','int','restricted_list','date','bool','url','float'));
END $$;
