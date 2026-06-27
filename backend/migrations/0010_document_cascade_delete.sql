-- Suppression en cascade des enfants quand un document parent est supprimé.
-- La FK document.parent était ON DELETE RESTRICT, ce qui bloquait la suppression
-- d'un document ayant des enfants. On passe à ON DELETE CASCADE : la suppression
-- d'un document supprime récursivement tous ses descendants.
ALTER TABLE document
    DROP CONSTRAINT document_parent_fkey,
    ADD  CONSTRAINT document_parent_fkey
         FOREIGN KEY (parent)
         REFERENCES document(doc_technical_key)
         ON DELETE CASCADE;
