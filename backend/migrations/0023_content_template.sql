-- Ajoute content_template sur functional_type.
-- Additif pur : ADD COLUMN nullable, aucune ligne existante rejetée.
-- Idempotent : IF NOT EXISTS.
ALTER TABLE functional_type ADD COLUMN IF NOT EXISTS content_template text;
