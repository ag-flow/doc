-- 0078_automation_workspace_optional.sql
--
-- La portée d'un automate est devenue un FILTRE comme les autres : rien de coché
-- dans la section « couverture de déclenchement » veut dire « aucun filtre de
-- portée », donc l'instance entière — au même titre qu'aucun bloc coché veut dire
-- tous les blocs. Un automate peut donc légitimement n'être rattaché à aucun
-- workspace.
--
-- `automation.workspace_technical_key` est la colonne d'origine, d'avant la table
-- `automation_workspace` qui porte la couverture multi-workspaces depuis 0056.
-- Elle n'est plus lue pour décider de quoi que ce soit : ni la visibilité
-- (`_VISIBLE` interroge `automation_workspace`), ni le périmètre du worker, ni
-- l'ordre d'évaluation. Elle n'est plus que projetée dans le DTO.
--
-- La garder NOT NULL obligerait à inventer un workspace « d'origine » pour un
-- automate qui n'en a délibérément aucun — c'est-à-dire à écrire une valeur qui
-- ment sur la portée réelle. On la rend donc nullable plutôt que de la remplir
-- pour satisfaire une contrainte qui n'a plus d'objet.
--
-- Aucune donnée n'est touchée : les automates existants gardent leur valeur.

ALTER TABLE automation
    ALTER COLUMN workspace_technical_key DROP NOT NULL;

COMMENT ON COLUMN automation.workspace_technical_key IS
    'Vestige d''avant la couverture multi-workspaces (0056). La portée réelle est '
    'dans automation_workspace ; NULL = aucun filtre de portée (toute l''instance).';
