-- 0043_document_dedup_key.sql
-- Clef de dédoublonnage d'un document : sha256 (hex) d'une clef texte
-- normalisée (trim + minuscules). Métadonnée d'identité posée sur le head
-- `document`, NON versionnée (elle ne suit pas l'historique de contenu).
--
-- Nullable et NON unique : l'unicité est décidée par l'appelant (p. ex. une
-- règle workflow qui teste l'existence avant de déposer), jamais imposée par
-- l'application — poser la même valeur sur deux documents est autorisé.
--
-- La clef en clair n'est jamais stockée : seule son empreinte l'est. Colonne
-- indexée (scopée workspace) pour la recherche via le tool MCP find_by_dedup_key.
ALTER TABLE document ADD COLUMN IF NOT EXISTS dedup_sha256 text;

CREATE INDEX IF NOT EXISTS document_dedup_sha256_idx
    ON document (workspace_technical_key, dedup_sha256)
    WHERE dedup_sha256 IS NOT NULL;
