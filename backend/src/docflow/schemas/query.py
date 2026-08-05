"""Contrat de requête unique (`QuerySpec`) — moteur de requête serveur.

Réutilisé par la table (filtres/tri d'entête), les requêtes nommées et la surface
MCP. Un `QuerySpec` décrit : périmètre (workspace/bloc), types d'objet, filtres
typés, tri multi-clé, projection des propriétés, pagination bornée.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

Operator = Literal[
    "eq",
    "contains",
    "starts_with",
    "lt",
    "gt",
    "between",
    "in",
    "before",
    "after",
]

# Opérateurs autorisés par type de propriété. Sert à la validation op↔type au
# moment de l'exécution (le type réel est résolu depuis les définitions du bloc).
OPS_BY_TYPE: dict[str, frozenset[str]] = {
    "text": frozenset({"eq", "contains", "starts_with"}),
    "url": frozenset({"eq", "contains", "starts_with"}),
    "int": frozenset({"eq", "lt", "gt", "between"}),
    "float": frozenset({"eq", "lt", "gt", "between"}),
    "date": frozenset({"eq", "before", "after", "between"}),
    "restricted_list": frozenset({"eq", "in"}),
    "bool": frozenset({"eq"}),
    "reference": frozenset({"eq"}),
}

MAX_PAGE_SIZE = 100


class FilterClause(BaseModel):
    """Un filtre sur une propriété. `value` pour les op à valeur unique ;
    `values` pour `in` (liste) et `between` (exactement [min, max])."""

    model_config = {"extra": "forbid"}

    prop: str
    op: Operator
    value: str | None = None
    values: list[str] | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> FilterClause:
        if self.op == "in":
            if not self.values:
                raise ValueError("op 'in' exige 'values' (liste non vide)")
        elif self.op == "between":
            if not self.values or len(self.values) != 2:
                raise ValueError("op 'between' exige 'values' = [min, max]")
        else:
            if self.value is None:
                raise ValueError(f"op '{self.op}' exige 'value'")
        return self


class SortKey(BaseModel):
    model_config = {"extra": "forbid"}

    # key = slug de propriété | 'title' | 'created_at' | 'updated_at'
    key: str
    dir: Literal["asc", "desc"] = "asc"


class QuerySpec(BaseModel):
    model_config = {"extra": "forbid"}

    workspace_slug: str
    block_slug: str
    type_slugs: list[str] | None = None
    filters: list[FilterClause] = []
    sort: list[SortKey] = []
    projection: list[str] | None = None
    page: int = 1
    page_size: int = 50

    @model_validator(mode="after")
    def _check_pagination(self) -> QuerySpec:
        if self.page < 1:
            raise ValueError("page doit être >= 1")
        if self.page_size < 1 or self.page_size > MAX_PAGE_SIZE:
            raise ValueError(f"page_size doit être entre 1 et {MAX_PAGE_SIZE}")
        return self


class BlockQueryBody(BaseModel):
    """Corps REST de POST .../blocks/{block}/query (workspace+bloc viennent du path)."""

    model_config = {"extra": "forbid"}

    type_slugs: list[str] | None = None
    filters: list[FilterClause] = []
    sort: list[SortKey] = []
    projection: list[str] | None = None
    page: int = 1
    page_size: int = 50
