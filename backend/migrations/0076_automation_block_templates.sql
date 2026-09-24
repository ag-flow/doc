-- 0076_automation_block_templates.sql
--
-- Un automate se restreint aujourd'hui par `block_slugs` — une liste de NOMS
-- figée. Créer un bloc oblige donc à se souvenir d'aller éditer chaque automate
-- concerné. Personne ne s'en souvient, et le symptôme n'est pas une erreur :
-- c'est un bloc qui n'est JAMAIS indexé, sans que rien ne le signale.
--
-- `block_templates` exprime l'intention plutôt que l'énumération : « tous les
-- blocs issus du template knowledge-base ». Un bloc créé depuis ce template
-- entre dans le périmètre sans aucun geste.
--
-- La provenance existe déjà : `functional_type.source_template` (migration
-- 0038), porté par le type RACINE du bloc (`data_block.functional_type_ref`).
--
-- UNION avec `block_slugs`, décision d'architecte du 2026-09-24 : les deux
-- colonnes énumèrent ce qui est COUVERT. Un bloc entre s'il est nommé OU s'il
-- vient d'un template listé. En intersection, un bloc nouveau n'entrerait
-- jamais seul — ce qui annulerait le bénéfice recherché.
--
-- Ajout additif, nullable par défaut : les automates existants gardent
-- exactement leur comportement (tableau vide = critère non posé).

ALTER TABLE automation
    ADD COLUMN IF NOT EXISTS block_templates text[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN automation.block_templates IS
    'Templates dont les blocs sont couverts (union avec block_slugs). '
    'Résolu via data_block -> functional_type.source_template.';
