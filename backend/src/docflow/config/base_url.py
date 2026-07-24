"""Base URL publique dérivée des requêtes portail (repli si non configurée).

Le worker d'automation tourne hors contexte requête : il ne peut pas dériver
l'URL de base lui-même. Un middleware la capture depuis les requêtes du portail
et la mémorise ici ; le worker l'utilise en repli quand `public_base_url` (env)
n'est pas renseignée, pour construire des liens de consultation absolus.
"""

from __future__ import annotations

_derived_base_url: str | None = None


def set_derived_base_url(url: str | None) -> None:
    """Mémorise la dernière base URL vue (ignore les valeurs vides)."""
    global _derived_base_url
    if url:
        _derived_base_url = url


def get_derived_base_url() -> str | None:
    return _derived_base_url


def effective_base_url(settings: object) -> str | None:
    """`public_base_url` configurée si présente, sinon la base dérivée du portail."""
    configured = getattr(settings, "public_base_url", None)
    if configured:
        return str(configured)
    return _derived_base_url
