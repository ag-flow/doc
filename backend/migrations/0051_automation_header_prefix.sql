-- =====================================================================
-- 0051_automation_header_prefix.sql  (additif)
-- Préfixe de valeur pour un header d'automate : permet le schéma HTTP Bearer
-- (Authorization: Bearer <clé>) où la valeur résolue du secret est préfixée.
-- NULL/'' = aucun préfixe (cas apiKey-in-header et headers constants).
-- =====================================================================
alter table automation_header add column if not exists value_prefix text;
