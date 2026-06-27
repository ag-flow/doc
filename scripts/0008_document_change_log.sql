-- =====================================================================
-- 0008_document_change_log.sql  (additif — ne réécrit rien)
-- Journal append-only des changements de documents, source du catch-up feed
-- (GET .../changes) qui permet à un externe de rattraper les webhooks loupés.
-- Curseur = seq (BIGINT séquence, strictement croissant, unique, total).
-- =====================================================================

create table document_change_log (
    seq         bigint generated always as identity primary key,   -- le curseur
    workspace_technical_key uuid not null
                references workspace(workspace_technical_key) on delete cascade,
    document_ref uuid not null,           -- PAS de FK : la ligne doit SURVIVRE à la
                                          -- suppression du document (sinon on perd le 'D')
    nature      text not null,            -- C | U | P | D (liste fermée) ; validé applicativement
    occurred_at timestamptz not null default now()
);

create index idx_change_log_ws_seq on document_change_log(workspace_technical_key, seq);
-- requête feed : WHERE workspace_technical_key = :ws AND seq > :since ORDER BY seq LIMIT :n

-- Alimentation : une ligne insérée DANS la transaction du write (21_RW) à chaque
--   C = création de document
--   U = nouvelle version de contenu (document_version)
--   P = nouvelle version de valeur de propriété (properties_value_version)
--   D = suppression de document (l'id est conservé ici, le document non)
-- L'insertion in-transaction garantit qu'aucun changement n'échappe au journal.
