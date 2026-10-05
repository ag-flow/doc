-- 0077_username_is_the_login.sql
--
-- L'email ne doit JAMAIS authentifier (STANDARD « Gestion des utilisateurs », U7) :
-- c'est un pivot d'identité, pas un identifiant de connexion. Jusqu'ici
-- `_SELECT_FOR_LOGIN` faisait `WHERE email = $1`.
--
-- La colonne `username` existe depuis 0021 et porte déjà un index unique (0027),
-- mais elle est restée NULLABLE et deux créateurs de comptes ne la renseignaient
-- pas : `admin/users/service.py` (création par un administrateur) et
-- `auth/invite.py` (invitation). Basculer la connexion sans backfill rendrait ces
-- comptes INCONNECTABLES — un lock-out silencieux, exactement ce que le garde-fou
-- anti-lock-out existe pour empêcher.
--
-- Backfill déterministe, sans boucle et sans risque de collision :
--   * partie locale de l'email si elle est libre ET non revendiquée par un autre
--     compte à backfiller (deux adresses `a@x` / `a@y` donnent la même base) ;
--   * sinon la base suffixée des 8 premiers caractères de l'id, qui est unique par
--     construction — donc aucune seconde passe nécessaire.
--
-- La colonne reste NULLABLE à dessein : un compte OIDC pur n'a pas besoin d'un
-- identifiant de connexion locale, et l'index unique de 0027 ignore les NULL. La
-- contrainte qui compte est portée par le code, au point de création.

UPDATE app_user u
SET username = CASE
        WHEN NOT EXISTS (
                 SELECT 1 FROM app_user o
                 WHERE o.username = split_part(u.email, '@', 1)
             )
         AND (
                 SELECT count(*) FROM app_user x
                 WHERE x.username IS NULL
                   AND split_part(x.email, '@', 1) = split_part(u.email, '@', 1)
             ) = 1
        THEN split_part(u.email, '@', 1)
        ELSE split_part(u.email, '@', 1) || '-' || left(u.id::text, 8)
    END
WHERE u.username IS NULL
  AND u.email IS NOT NULL;

COMMENT ON COLUMN app_user.username IS
    'Identifiant de CONNEXION locale. L''email est un pivot d''identité et '
    'n''authentifie jamais (STANDARD utilisateurs U7). NULL admis pour un compte '
    'sans connexion locale (OIDC pur).';
