-- =====================================================================
-- 0007_webhook_subscription.sql  (additif — ne réécrit rien)
-- Abonnements webhook scopés au workspace : pousser un event vers un service
-- externe quand un document est créé/modifié/supprimé.
-- Livraison asynchrone best-effort (pas de retry, pas d'outbox).
-- Headers chiffrés au repos (champ chiffré, pas de vault).
-- =====================================================================

create table webhook_subscription (
    id          uuid primary key default gen_random_uuid(),
    workspace_technical_key uuid not null
                references workspace(workspace_technical_key) on delete cascade,
    label       text not null,
    url         text not null,                  -- cible du POST ; peut contenir {id_document}
    headers_encrypted text,                     -- JSON des headers, CHIFFRÉ (Fernet) ; null = aucun
    events      text[] not null,                -- sous-ensemble de
                                                -- {document.created, document.updated, document.deleted}
    active      boolean not null default true,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index idx_webhook_ws on webhook_subscription(workspace_technical_key);

-- events : validé applicativement (pydantic) contre la liste fermée des event types.
-- headers_encrypted : déchiffré uniquement à l'émission (worker), jamais loggé.
-- Frontière assumée : url + headers vivent ici PROVISOIREMENT ; le jour où la
-- notion de "web service" existe, le hook pointera un service (qui portera l'auth).
