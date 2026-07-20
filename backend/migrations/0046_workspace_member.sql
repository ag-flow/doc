-- 0046_workspace_member.sql
-- Contrôle d'accès par utilisateur au niveau workspace (unité d'isolation).
--
-- Un utilisateur accède à un workspace ET à tout son contenu s'il est :
--   - superadmin (app_user.is_admin), OU
--   - owner (workspace.owner_id == user.id), OU
--   - membre (une ligne ici).
-- Les objets internes (blocs, documents, propriétés) héritent de l'accès du
-- workspace : aucun champ owner ne les porte.
--
-- Additive et idempotente (CREATE TABLE IF NOT EXISTS). Cascade sur la
-- suppression du workspace ET de l'utilisateur : aucune ligne orpheline.
CREATE TABLE IF NOT EXISTS workspace_member (
    workspace_technical_key uuid NOT NULL
        REFERENCES workspace(workspace_technical_key) ON DELETE CASCADE,
    user_id uuid NOT NULL
        REFERENCES app_user(id) ON DELETE CASCADE,
    role text NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'member')),
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_technical_key, user_id)
);
