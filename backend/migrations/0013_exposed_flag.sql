-- Marque qu'un document (ou un bloc entier) est exposé en lecture publique.
-- Le flag se propage en cascade à tous les descendants lors de sa modification.
ALTER TABLE data_block ADD COLUMN IF NOT EXISTS exposed boolean NOT NULL DEFAULT false;
ALTER TABLE document   ADD COLUMN IF NOT EXISTS exposed boolean NOT NULL DEFAULT false;
