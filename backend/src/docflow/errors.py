from __future__ import annotations


class DependentsConflictError(Exception):
    """Suppression destructrice refusée : des dépendants seraient détruits en cascade.

    Levée par les services de suppression (type, bloc, propriété) quand des
    dépendants existent et que l'appelant n'a pas fourni ``confirm=true``.
    Convertie en réponse HTTP 409 par le handler enregistré dans ``app.py`` :
    ``{"detail": ..., "dependents": n, "need_confirm": true}``.
    """

    def __init__(self, detail: str, dependents: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.dependents = dependents
