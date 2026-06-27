-- =====================================================================
-- 0012_automation.sql  (additif — ne réécrit rien)
-- Configuration d'un automate : sur tel changement de document (C/U), appeler
-- une API distante décrite par un contrat OpenAPI, avec débounce en fenêtre
-- glissante. Headers en clair OU référence au coffre (xor), modèle repris du
-- pattern WebhookHeaderIn d'ag-flow.rag (value xor vault).
-- =====================================================================

create table automation (
    id          uuid primary key default gen_random_uuid(),
    workspace_technical_key uuid not null
                references workspace(workspace_technical_key) on delete cascade,
    label       text not null,
    active      boolean not null default true,
    on_create   boolean not null default false,   -- nature C
    on_update   boolean not null default false,   -- nature U  (P et D plus tard)
    delay_minutes integer not null default 0,      -- débounce fenêtre glissante (0 = immédiat)
    contract_ref uuid references openapi_contract(id) on delete restrict,
    operation_id text,                             -- opération choisie dans le contrat
    url         text not null,                     -- URL réelle (base + path rempli par l'utilisateur)
    http_method text not null,                     -- GET/POST/... (issu de l'opération)
    body_template text,                            -- modèle JSON avec variables ; null si pas de body
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index idx_automation_ws on automation(workspace_technical_key);

create table automation_header (
    id          uuid primary key default gen_random_uuid(),
    automation_ref uuid not null references automation(id) on delete cascade,
    name        text not null,
    value       text,             -- valeur en clair        (xor secret_ref)
    secret_ref  text,             -- référence au coffre     (xor value) ; résolu à l'exécution
    required    boolean not null default false,    -- issu du contrat (présence vérifiée, pas le contenu)
    enabled     boolean not null default true,
    unique (automation_ref, name),
    check (not (value is not null and secret_ref is not null))
);
