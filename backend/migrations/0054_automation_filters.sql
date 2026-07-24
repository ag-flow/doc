-- =====================================================================
-- 0054_automation_filters.sql  (additif)
-- Filtres additionnels (combinés en AND avec les eventCodes) : restreindre le
-- déclenchement à certains blocs et/ou certains types de document. Vide = tous.
-- =====================================================================
alter table automation add column if not exists block_slugs text[] not null default '{}';
alter table automation add column if not exists functional_type_slugs text[] not null default '{}';
