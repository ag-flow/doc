-- =====================================================================
-- 0011_openapi_contract.sql  (additif — ne réécrit rien)
-- Contrats OpenAPI importés, servant à décrire les méthodes appelables par
-- les automates (sélection d'opération + préremplissage du body). Global
-- (réutilisable entre workspaces). Bouton refresh = re-fetch + ré-écriture.
-- =====================================================================

create table openapi_contract (
    id          uuid primary key default gen_random_uuid(),
    label       text not null,
    source_url  text,                       -- pour le refresh (re-fetch) ; null si import manuel
    version     text,                        -- info.version du contrat (affichage)
    raw_spec    jsonb not null,              -- le contrat OpenAPI complet
    imported_at timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
