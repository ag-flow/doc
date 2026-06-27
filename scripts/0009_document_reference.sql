-- =====================================================================
-- 0009_document_reference.sql  (additif — ne réécrit rien)
-- Liens document -> document, à FK MOLLE. Philosophie "détecter, pas empêcher" :
-- aucun ON DELETE sur la cible, les liens peuvent devenir orphelins librement,
-- on les retrouve par anti-join. Table DÉRIVÉE du contenu (reconstruite à chaque save).
-- =====================================================================

create table document_reference (
    id          uuid primary key default gen_random_uuid(),
    source_ref  uuid not null references document(doc_technical_key) on delete cascade,
                                          -- le doc qui cite ; s'il part, ses refs partent
    target_ref  uuid not null,            -- FK MOLLE : aucune contrainte -> peut devenir orpheline
    target_label text,                    -- texte du lien au moment du save (affichage même orphelin)
    workspace_technical_key uuid not null
                references workspace(workspace_technical_key) on delete cascade,  -- du source, dénormalisé
    created_at  timestamptz not null default now(),
    unique (source_ref, target_ref)
);

create index idx_docref_target on document_reference(target_ref);  -- anti-join de détection d'orphelins
create index idx_docref_ws     on document_reference(workspace_technical_key);

-- Détection des orphelins :
--   select r.* from document_reference r
--   left join document d on d.doc_technical_key = r.target_ref
--   where d.doc_technical_key is null;
