"""Coercition tolérante des arguments MCP.

Beaucoup de clients LLM sérialisent les booléens en chaîne (`"true"`/`"false"`).
Un simple `bool(args.get(k))` est alors PIÈGE : `bool("false")` vaut True (chaîne
non vide). `as_bool` interprète explicitement les deux formes et retombe sur un
défaut pour toute valeur ambiguë ou absente.
"""

from __future__ import annotations

_TRUE = {"true", "1", "yes", "oui", "on"}
_FALSE = {"false", "0", "no", "non", "off", ""}


def as_bool(raw: object, *, default: bool = False) -> bool:
    """Booléen tolérant : `True`/`False`, ou chaîne « true »/« false » (et variantes).

    Toute valeur absente (None) ou non reconnue retombe sur `default`.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in _TRUE:
            return True
        if value in _FALSE:
            return False
        return default
    if raw is None:
        return default
    return default
