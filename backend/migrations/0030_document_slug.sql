-- =====================================================================
-- 0030_document_slug.sql — ajout d'un slug stable sur document
--
-- Le slug sert à nommer les fichiers lors de l'export git (backup contenu).
-- Unicité parmi les frères (même workspace + même parent) :
--   - racines   (parent IS NULL)  → index partiel WHERE parent IS NULL
--   - non-racines (parent NOT NULL) → contrainte UNIQUE (workspace, parent, slug)
-- Additive : nullable d'abord (les documents existants n'ont pas de slug).
-- =====================================================================

ALTER TABLE document ADD COLUMN IF NOT EXISTS slug TEXT;

-- Unicité parmi les documents racines d'un workspace
CREATE UNIQUE INDEX IF NOT EXISTS document_slug_root_uix
    ON document (workspace_technical_key, slug)
    WHERE parent IS NULL AND slug IS NOT NULL;

-- Unicité parmi les frères (même parent)
CREATE UNIQUE INDEX IF NOT EXISTS document_slug_sibling_uix
    ON document (workspace_technical_key, parent, slug)
    WHERE parent IS NOT NULL AND slug IS NOT NULL;

-- Index de lookup direct par slug dans un workspace (utile pour les URLs)
CREATE INDEX IF NOT EXISTS document_slug_ws_idx
    ON document (workspace_technical_key, slug)
    WHERE slug IS NOT NULL;
