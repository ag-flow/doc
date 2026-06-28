-- Spec 38 — MREL : type de propriété 'reference'
-- La valeur est un doc_technical_key ; target_functional_type_ref (optionnel) restreint le type cible.
-- Stocké dans properties_value_version.target_document_ref (errata 02b).
DO $$
BEGIN
    -- Ajouter target_document_ref sur properties_value_version
    ALTER TABLE properties_value_version
        ADD COLUMN IF NOT EXISTS target_document_ref uuid
        REFERENCES document(doc_technical_key) ON DELETE SET NULL;

    -- Ajouter target_functional_type_ref sur properties_defs (contrainte optionnelle)
    ALTER TABLE properties_defs
        ADD COLUMN IF NOT EXISTS target_functional_type_ref uuid
        REFERENCES functional_type(id) ON DELETE SET NULL;

    -- Étendre la contrainte CHECK sur properties_defs.type
    ALTER TABLE properties_defs DROP CONSTRAINT IF EXISTS properties_defs_type_check;
    ALTER TABLE properties_defs ADD CONSTRAINT properties_defs_type_check
        CHECK (type IN ('text','int','restricted_list','date','bool','url','float','reference'));
END $$;
