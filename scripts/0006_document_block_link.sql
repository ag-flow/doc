-- =====================================================================
-- 0006_document_block_link.sql  (additif — ne réécrit pas 0001)
-- Chaînon manquant : un document appartient à un data_block (le conteneur
-- racine de son arbre). Absent du 0001, requis par le flux "dans le bloc -> Add".
-- Base vierge de données : table vide, donc NOT NULL direct possible.
-- =====================================================================

alter table document
    add column data_block_ref uuid not null
        references data_block(id) on delete restrict;

create index idx_document_block on document(data_block_ref);

-- data_block_ref DÉNORMALISÉ sur chaque document (comme workspace_technical_key) :
--   "tous les documents du bloc B" = WHERE data_block_ref = B, à plat, sans jointure.
-- Invariant (tenu applicativement à la création — cf. spec 23_MTC) :
--   data_block_ref d'un document == data_block_ref de son parent
--   (un enfant hérite le bloc de son parent ; à la racine, = le bloc choisi).
