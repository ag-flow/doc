"""Journal des appels d'outils MCP — issue comprise.

Avant ce module, `_dispatch_tool` écrivait une ligne `mcp_call_tool` à l'ENTRÉE
et plus rien ensuite. Un appel qui échouait repartait au client marqué
`isError`, et ne laissait aucune trace : sur sept jours d'exploitation, zéro
ligne d'erreur pour ~1000 appels par bucket. Ce zéro ne disait pas « tout va
bien », il disait « on ne regarde pas ».

C'est le même mode de panne que le debounce des automates, où « en attente » et
« en panne » produisaient des logs identiques — c'est-à-dire aucun.

Ce qu'on journalise, et pourquoi pas plus : métadonnées d'appel et **noms** des
arguments, jamais leurs valeurs. Les arguments MCP transportent des contenus de
documents, des titres et des valeurs de propriétés : ce sont des données
utilisateur, elles n'ont rien à faire dans un agrégateur de logs. Les noms
suffisent à savoir comment l'appel était formé.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from docflow.mcp import errors, session

log = structlog.get_logger(__name__)

# Arguments dont le NOM seul identifie déjà le périmètre visé, et qui sont des
# identifiants publics (pas du contenu) : eux, on les logue en valeur, car sans
# eux « not_found » ne dit pas de quoi on parle.
_SAFE_VALUE_KEYS = ("workspace_slug", "block_slug", "template_slug")


def _caller() -> dict[str, Any]:
    """Qui appelle — sans jamais lire la clé API elle-même."""
    current = session.current_session()
    if current is None:
        return {}
    acting = current.acting_user
    return {
        "owner": acting.email or str(acting.id),
        # Une session OBO agit pour un humain distinct du porteur de la clé :
        # le distinguer évite d'attribuer l'appel au mauvais acteur.
        "on_behalf": current.actor_user is not None,
    }


def _scope(arguments: dict[str, object]) -> dict[str, Any]:
    return {key: arguments[key] for key in _SAFE_VALUE_KEYS if isinstance(arguments.get(key), str)}


class ToolCall:
    """Mesure un appel et en journalise l'issue, quoi qu'il arrive.

    S'utilise en gestionnaire de contexte : la sortie écrit la ligne, y compris
    quand le corps lève. Une exception qui remonte est journalisée `outcome
    =exception` — c'est le seul cas où la stack a de la valeur, donc le seul où
    on la demande (`exc_info`).
    """

    def __init__(self, name: str, arguments: dict[str, object]) -> None:
        self.name = name
        self.arguments = arguments
        self.code: str | None = None
        self._started = 0.0

    def __enter__(self) -> ToolCall:
        self._started = time.perf_counter()
        return self

    def record(self, payload: object) -> None:
        """Retient le code d'erreur du résultat (None si l'appel a réussi)."""
        self.code = errors.code_of(payload)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        duration_ms = round((time.perf_counter() - self._started) * 1000, 1)
        fields: dict[str, Any] = {
            "tool": self.name,
            "duration_ms": duration_ms,
            "arg_keys": sorted(self.arguments),
            **_scope(self.arguments),
            **_caller(),
        }
        if exc_type is not None:
            log.error("mcp_tool_call_done", outcome="exception", **fields, exc_info=True)
        elif self.code is not None:
            # `warning` et non `error` : un refus d'argument ou un document
            # introuvable est un échec de l'APPELANT, pas une panne du serveur.
            # Les confondre rendrait le niveau `error` inexploitable en alerte.
            level = log.error if self.code == errors.INTERNAL else log.warning
            level("mcp_tool_call_done", outcome="error", code=self.code, **fields)
        else:
            log.info("mcp_tool_call_done", outcome="ok", **fields)
