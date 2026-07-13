-- =====================================================================
-- 0038_functional_type_source_template.sql
--
-- Provenance d'un type fonctionnel : slug du template qui l'a créé ou
-- mis à jour via un import. NULL = type créé manuellement, ou importé
-- avant cette migration — dans ce cas la provenance est réconciliée au
-- prochain import du template (voir templates/importer.py).
-- =====================================================================

ALTER TABLE functional_type
    ADD COLUMN source_template text;
