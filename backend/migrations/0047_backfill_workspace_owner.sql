-- 0047_backfill_workspace_owner.sql
-- Rattache les workspaces SANS propriétaire (owner_id NULL) au premier admin
-- LOCAL (bootstrap / break-glass : is_admin + password_hash + actif, le plus
-- ancien). Garanti d'exister sur une instance déjà configurée (garde
-- anti-lock-out : le dernier admin local ne peut être ni désactivé ni supprimé).
--
-- Contexte : depuis 0046 (contrôle d'accès), un workspace sans owner n'est
-- accessible qu'aux superadmins. Ce backfill redonne un propriétaire concret
-- aux workspaces créés AVANT le contrôle d'accès, sans les supprimer.
--
-- Instance vierge : aucun workspace n'existe encore à l'application → no-op.
-- Idempotent : rejoué, plus aucun owner_id n'est NULL → aucune ligne modifiée.
-- Le garde EXISTS évite d'écrire owner_id = NULL si (improbable) aucun admin
-- local n'existe.
UPDATE workspace
SET owner_id = (
        SELECT id FROM app_user
        WHERE is_admin AND password_hash IS NOT NULL AND NOT disabled
        ORDER BY created_at
        LIMIT 1
    )
WHERE owner_id IS NULL
  AND EXISTS (
        SELECT 1 FROM app_user
        WHERE is_admin AND password_hash IS NOT NULL AND NOT disabled
    );
