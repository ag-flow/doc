"""DTOs du mode browse arbre (list_block_tree).

Un `BlockTreePage` pagine les **racines** d'un bloc (≤100/page) ; chaque racine
porte son sous-arbre complet (`children` récursif) et les valeurs de propriétés de
chaque nœud. Réutilise `PropertyValueBrief` (même forme aplatie que les objets).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from docflow.schemas.introspection import PropertyValueBrief


class BlockTreeNode(BaseModel):
    """Un nœud de l'arbre : le document + ses valeurs + ses enfants directs."""

    id: str
    title: str
    functional_type_slug: str | None
    parent_id: str | None
    updated_at: datetime | None = None
    updated_by: str | None = None
    properties: list[PropertyValueBrief]
    children: list[BlockTreeNode]


class BlockTreePage(BaseModel):
    """Page de racines d'un bloc, chacune portant son sous-arbre.

    `total` et `has_next` comptent les **racines** uniquement : les enfants d'une
    racine incluse ne consomment pas le `page_size`.
    """

    block_slug: str
    page: int
    page_size: int
    total: int
    has_next: bool
    roots: list[BlockTreeNode]


BlockTreeNode.model_rebuild()
