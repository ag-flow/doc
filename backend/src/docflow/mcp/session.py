from __future__ import annotations

import contextvars
from dataclasses import dataclass

from docflow.apikeys.schemas import ApiProfileScopeOut
from docflow.schemas.auth import AuthUser


@dataclass(frozen=True)
class McpSession:
    """Identité et droits liés à une session MCP.

    ``api_key_scopes`` à None = session ouverte par JWT (accès complet, comme
    l'API REST). Une liste (même vide) = session ouverte par clé API : les
    outils sont restreints au périmètre du profil, sauf profil admin.
    """

    user: AuthUser
    api_key_scopes: list[ApiProfileScopeOut] | None = None
    api_key_admin: bool = False
    # Principal humain résolu par OBO (portail, en-têtes signés). None = pas
    # d'OBO : l'identité agissante est celle de la clé API (``user``).
    actor_user: AuthUser | None = None

    @property
    def unrestricted(self) -> bool:
        """Vrai si la session n'est pas contrainte par un profil de clé API."""
        return self.api_key_scopes is None or self.api_key_admin

    @property
    def acting_user(self) -> AuthUser:
        """Identité agissante : l'humain OBO s'il existe, sinon l'identité de la clé.

        Ne change JAMAIS les droits : toute décision d'accès se juge sur ``user``
        (porteur de la clé), car l'acteur OBO est forgeable par ce porteur.
        Sert uniquement à l'estampillage de propriété (owner_id, created_by).
        """
        return self.actor_user or self.user


# Session authentifiée de la connexion MCP courante. Positionnée par le routeur
# SSE (`mcp/router.py`) juste avant `mcp_server.run` ; la boucle de dispatch des
# messages tourne dans des tâches filles de ce contexte, la ContextVar est donc
# héritée jusqu'aux handlers d'outils. Chaque connexion SSE vit dans sa propre
# tâche/contexte : aucune contamination entre sessions.
_current_session: contextvars.ContextVar[McpSession | None] = contextvars.ContextVar(
    "mcp_current_session", default=None
)


def set_current_session(
    session: McpSession | None,
) -> contextvars.Token[McpSession | None]:
    """Lie la session authentifiée à la connexion MCP courante (appelé par le SSE)."""
    return _current_session.set(session)


def reset_current_session(token: contextvars.Token[McpSession | None]) -> None:
    _current_session.reset(token)


def current_session() -> McpSession | None:
    return _current_session.get()


def require_identity() -> AuthUser:
    """Identité de l'appelant MCP ; erreur si la session n'est pas authentifiée."""
    session = _current_session.get()
    if session is None:
        raise RuntimeError("identité de session MCP indisponible")
    return session.user


def acting_identity() -> AuthUser:
    """Identité agissante (humain OBO ou identité de la clé) pour l'estampillage.

    Erreur si la session n'est pas authentifiée. Les droits se jugent sur
    ``require_identity`` (porteur de la clé) ; ceci ne sert qu'à l'attribution
    de propriété (owner_id, created_by) — jamais à une décision d'accès.
    """
    session = _current_session.get()
    if session is None:
        raise RuntimeError("identité de session MCP indisponible")
    return session.acting_user
