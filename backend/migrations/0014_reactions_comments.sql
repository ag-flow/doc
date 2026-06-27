-- Réactions (like/dislike) sur les documents
CREATE TABLE document_reaction (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_ref uuid     NOT NULL REFERENCES document(doc_technical_key) ON DELETE CASCADE,
    user_ref     uuid     NOT NULL REFERENCES admin_user(id) ON DELETE CASCADE,
    nature       smallint NOT NULL CHECK (nature IN (1, -1)),
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_ref, user_ref)
);

CREATE INDEX ON document_reaction (document_ref, nature, created_at DESC);

-- Commentaires sur les documents
CREATE TABLE document_comment (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_ref uuid NOT NULL REFERENCES document(doc_technical_key) ON DELETE CASCADE,
    user_ref     uuid NOT NULL REFERENCES admin_user(id) ON DELETE CASCADE,
    body         text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON document_comment (document_ref, created_at);

-- Réactions (like/dislike) sur les commentaires
CREATE TABLE comment_reaction (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    comment_ref uuid     NOT NULL REFERENCES document_comment(id) ON DELETE CASCADE,
    user_ref    uuid     NOT NULL REFERENCES admin_user(id) ON DELETE CASCADE,
    nature      smallint NOT NULL CHECK (nature IN (1, -1)),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (comment_ref, user_ref)
);

CREATE INDEX ON comment_reaction (comment_ref, nature, created_at DESC);
