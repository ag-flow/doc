-- =====================================================================
-- 0010_document_title_search.sql  (additif — ne réécrit rien)
-- Recherche de documents par TITRE pour l'autocomplétion du menu de lien.
-- pg_trgm : tolère préfixes/frappe partielle/fautes -> adapté à la recherche
-- caractère par caractère. Le CONTENU n'est PAS indexé (il attendra le RAG).
--
-- À exécuter DANS la base docflow : CREATE EXTENSION est scopé à la base
-- (le moteur héberge aussi le RAG et le portail devpod, mais en bases séparées
--  avec chacune ses propres extensions ; pas de jointure cross-base).
-- =====================================================================

create extension if not exists pg_trgm;

create index idx_document_title_trgm
    on document using gin (title gin_trgm_ops);
-- recherche : WHERE workspace_technical_key = :ws AND title ILIKE '%' || :q || '%'
-- (le filtre workspace s'appuie sur idx_document_ws déjà présent)
