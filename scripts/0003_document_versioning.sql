-- =====================================================================
-- 0003_document_versioning.sql  (additif — ne réécrit pas 0001)
-- Versioning du CONTENU du document (audit/historique, consultation).
-- Le contenu part dans une table de version numérotée. Le head (document)
-- garde le titre dénormalisé (arbre à plat) et un compteur `version`.
-- Base vierge de données : les DROP ne migrent rien.
-- =====================================================================

create table document_version (
    version_technical_key uuid primary key default gen_random_uuid(),
    document_ref   uuid not null references document(doc_technical_key) on delete cascade,
    version_number integer not null,
    title          text not null,
    content        text,                       -- ex-document.contenu
    created_at     timestamptz not null default now(),
    unique (document_ref, version_number)
);

alter table document add column version integer not null default 1;  -- numéro courant
alter table document drop column contenu;                            -- déplacé dans document_version.content
-- CONSERVÉS volontairement :
--   document.title       -> titre courant dénormalisé (lecture d'arbre sans jointure)
--   document.updated_at  -> bumpé à chaque nouvelle version (dernière modif sans jointure)

create index idx_docversion_doc on document_version(document_ref);
-- la version courante = WHERE document_ref = D AND version_number = document.version
-- (lookup direct via l'index UNIQUE(document_ref, version_number))
