-- Références inter-documents à FK molle
-- source_ref : FK dure avec CASCADE (le citant fait autorité sur ses liens)
-- target_ref : pas de REFERENCES (la cible peut disparaître → orphelin détecté par anti-join)
-- target_label : texte du lien conservé même si la cible disparaît
CREATE TABLE document_reference (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_ref              uuid NOT NULL REFERENCES document(doc_technical_key) ON DELETE CASCADE,
    target_ref              uuid,
    target_label            text NOT NULL,
    workspace_technical_key uuid NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_ref, target_ref)
);

CREATE INDEX ON document_reference (target_ref);
CREATE INDEX ON document_reference (workspace_technical_key, source_ref);
