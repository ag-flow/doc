-- =====================================================================
-- 0033 — Change feed élargi à la structure (types, propriétés, blocs,
-- templates) pour que les sessions actives détectent toute évolution.
--
-- Additif : document_ref devient nullable (les entrées structure ne
-- pointent pas un document) ; entity_kind qualifie l'entité touchée.
-- Natures inchangées (C/U/P/D) : C/U/D valent pour toutes les entités,
-- P reste réservé aux documents (invariant applicatif, cf. changelog.py).
-- =====================================================================

ALTER TABLE document_change_log
    ALTER COLUMN document_ref DROP NOT NULL;

ALTER TABLE document_change_log
    ADD COLUMN entity_kind text NOT NULL DEFAULT 'document'
        CHECK (entity_kind IN ('document', 'type', 'property', 'block', 'template'));

-- entity_ref : identifiant de l'entité structure touchée (uuid du type,
-- de la def, du bloc… ; NULL pour un import de template global).
ALTER TABLE document_change_log
    ADD COLUMN entity_ref uuid;

-- Cohérence : une entrée document porte document_ref, une entrée
-- structure n'en porte pas.
ALTER TABLE document_change_log
    ADD CONSTRAINT chk_changelog_document_ref
        CHECK ((entity_kind = 'document') = (document_ref IS NOT NULL));
