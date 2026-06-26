-- =====================================================================
-- 0004_property_value_versioning.sql  (additif — ne réécrit pas 0001)
-- Même patron que 0003 pour les VALEURS de propriété : la valeur part dans
-- une table de version numérotée. Le head (properties_values) devient une
-- identité pure (document_ref, property_def_ref, version, workspace).
-- Base vierge de données : les DROP ne migrent rien.
-- =====================================================================

create table properties_value_version (
    version_technical_key uuid primary key default gen_random_uuid(),
    property_value_ref uuid not null references properties_values(id) on delete cascade,
    version_number     integer not null,
    value              text,                   -- text / int
    allowed_value_ref  uuid references properties_allowed_values(id) on delete restrict,  -- restricted_list
    created_at         timestamptz not null default now(),
    unique (property_value_ref, version_number),
    check (not (value is not null and allowed_value_ref is not null))   -- jamais les deux
);

alter table properties_values add column version integer not null default 1;  -- numéro courant

-- value / allowed_value_ref descendent dans la table de version.
--   DROP value            retire aussi le CHECK qui le référençait
--   DROP allowed_value_ref retire aussi l'index idx_pvalues_allowed
alter table properties_values drop column value;
alter table properties_values drop column allowed_value_ref;

-- Head = identité pure : les deux timestamps sont dérivables de la table de
-- version (création = 1re version, modif = version courante). On les retire.
alter table properties_values drop column created_at;
alter table properties_values drop column updated_at;

create index idx_pvalue_version_pv      on properties_value_version(property_value_ref);
create index idx_pvalue_version_allowed on properties_value_version(allowed_value_ref);
-- idx_..._allowed ré-ancre la requête board "tous les docs en statut X" :
-- properties_values (head, porte workspace + version)
--   JOIN properties_value_version ON (property_value_ref = head.id
--                                     AND version_number = head.version)
--   WHERE allowed_value_ref = X
