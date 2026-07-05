from __future__ import annotations

from docflow.apikeys.schemas import ApiProfileScopeOut


def scope_allows(
    scopes: list[ApiProfileScopeOut],
    ws_slug: str,
    block_slug: str | None = None,
    write: bool = False,
) -> bool:
    """Vérifie qu'au moins un scope du profil couvre (workspace, bloc, écriture).

    Un scope au niveau workspace (block_slug None) couvre tous les blocs ;
    un scope au niveau bloc ne couvre que ce bloc. Logique unique, partagée
    entre l'API REST (check_api_key_scope) et les outils MCP.
    """
    for scope in scopes:
        if scope.workspace_slug != ws_slug:
            continue
        if scope.block_slug is not None and scope.block_slug != block_slug:
            continue
        if write and scope.read_only:
            continue
        return True
    return False


def allowed_workspace_slugs(scopes: list[ApiProfileScopeOut]) -> set[str]:
    """Ensemble des workspaces visibles par le profil (tous niveaux confondus)."""
    return {s.workspace_slug for s in scopes}
