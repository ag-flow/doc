-- Recherche de titres par trigramme (pg_trgm)
-- Requiert que l'utilisateur DB ait les droits CREATE EXTENSION (superuser ou pg_extension_owner).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_document_title_trgm
    ON document USING gin (title gin_trgm_ops);
