-- =====================================================================
-- 0039_normalize_git_repo.sql
--
-- remote_point.git_repo doit contenir « org/nom » : les valeurs héritées
-- où une URL avait été collée telle quelle (https://…, git@…:…)
-- composaient une URL de clone invalide
-- (« git@host:https://….git.git » → protocol not supported).
-- Normalisation one-shot des lignes existantes ; la validation
-- applicative (remote/schemas.py::_normalize_git_repo) empêche
-- désormais toute nouvelle valeur invalide.
-- =====================================================================

UPDATE remote_point
SET git_repo = regexp_replace(
        regexp_replace(git_repo, '\.git/?$', ''),
        '^.*[:/](([^/:]+)/([^/:]+))$', '\1'
    ),
    updated_at = now()
WHERE point_type = 'git'
  AND git_repo IS NOT NULL
  AND git_repo !~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$';
