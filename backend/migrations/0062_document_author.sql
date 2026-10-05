-- Auteur de la dernière écriture d'un document (libellé affichable, pas une
-- FK : l'auteur peut être un agent OBO dont le compte n'existe pas dans
-- app_user). NULL = écriture antérieure à la colonne ou auteur inconnu.
ALTER TABLE document ADD COLUMN IF NOT EXISTS updated_by text;
