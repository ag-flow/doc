-- Suppression en cascade des types fonctionnels.
-- Toutes les FK référençant functional_type (ou ses dépendants) étaient
-- ON DELETE RESTRICT, ce qui empêchait la suppression d'un type dès qu'il
-- avait des propriétés, des blocs, des documents ou des valeurs associés.
--
-- Chaîne de cascade souhaitée :
--   functional_type → child types (CASCADE)
--   functional_type → data_block (CASCADE) → document (CASCADE)
--   functional_type → properties_defs (déjà CASCADE) → properties_values (CASCADE)
--   data_block → document (CASCADE) → properties_values via document_ref (CASCADE)
--   properties_allowed_values → properties_values.allowed_value_ref (SET NULL)
--   document.functional_type_ref (SET NULL, le document reste lisible sans type)

-- 1. Types enfants : RESTRICT → CASCADE
ALTER TABLE functional_type
    DROP CONSTRAINT functional_type_parent_fkey,
    ADD  CONSTRAINT functional_type_parent_fkey
         FOREIGN KEY (parent) REFERENCES functional_type(id) ON DELETE CASCADE;

-- 2. Blocs liés au type : RESTRICT → CASCADE
ALTER TABLE data_block
    DROP CONSTRAINT data_block_functional_type_ref_fkey,
    ADD  CONSTRAINT data_block_functional_type_ref_fkey
         FOREIGN KEY (functional_type_ref) REFERENCES functional_type(id) ON DELETE CASCADE;

-- 3. Blocs enfants : RESTRICT → CASCADE
ALTER TABLE data_block
    DROP CONSTRAINT data_block_parent_fkey,
    ADD  CONSTRAINT data_block_parent_fkey
         FOREIGN KEY (parent) REFERENCES data_block(id) ON DELETE CASCADE;

-- 4. Documents liés à un bloc : RESTRICT → CASCADE
ALTER TABLE document
    DROP CONSTRAINT document_data_block_ref_fkey,
    ADD  CONSTRAINT document_data_block_ref_fkey
         FOREIGN KEY (data_block_ref) REFERENCES data_block(id) ON DELETE CASCADE;

-- 5. Type d'un document : RESTRICT → SET NULL (le document reste sans type)
ALTER TABLE document
    DROP CONSTRAINT document_functional_type_ref_fkey,
    ADD  CONSTRAINT document_functional_type_ref_fkey
         FOREIGN KEY (functional_type_ref) REFERENCES functional_type(id) ON DELETE SET NULL;

-- 6. Valeurs de propriété → définition : RESTRICT → CASCADE
ALTER TABLE properties_values
    DROP CONSTRAINT properties_values_property_def_ref_fkey,
    ADD  CONSTRAINT properties_values_property_def_ref_fkey
         FOREIGN KEY (property_def_ref) REFERENCES properties_defs(id) ON DELETE CASCADE;

-- 7. Valeurs de propriété → valeur autorisée : RESTRICT → SET NULL
ALTER TABLE properties_values
    DROP CONSTRAINT properties_values_allowed_value_ref_fkey,
    ADD  CONSTRAINT properties_values_allowed_value_ref_fkey
         FOREIGN KEY (allowed_value_ref) REFERENCES properties_allowed_values(id) ON DELETE SET NULL;
