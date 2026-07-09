"""DTOs des primitives d'introspection et de query de bloc (épic MCP docflow).

Trois primitives, indépendantes des slugs (découverte dynamique) :
  - introspection de schéma : list_block_properties (sans doc_id) ;
  - listing paginé des objets d'un bloc avec leurs valeurs ;
  - query filtrée paginée sur propriété.
"""

from __future__ import annotations

from pydantic import BaseModel


class AllowedValueBrief(BaseModel):
    slug: str
    label: str


class BlockPropertyOut(BaseModel):
    prop_slug: str
    label: str
    type: str
    required: bool
    default_value: str | None = None
    # Renseigné uniquement pour type == "restricted_list".
    allowed_values: list[AllowedValueBrief] | None = None


class BlockTypePropertiesOut(BaseModel):
    functional_type_slug: str
    label: str
    # True pour le type racine du bloc ; les autres sont des types imbriqués autorisés.
    is_block_root: bool
    properties: list[BlockPropertyOut]


class BlockPropertiesOut(BaseModel):
    """Schéma de propriétés d'un bloc, groupé par type fonctionnel.

    Couvre le type racine du bloc et ses descendants dans la hiérarchie des types
    (les seuls types instanciables dans le bloc), pour que la découverte serve aussi
    le pilotage des documents imbriqués (features/stories), pas seulement la racine.
    """

    block_slug: str
    root_type_slug: str
    types: list[BlockTypePropertiesOut]


class PropertyValueBrief(BaseModel):
    """Valeur d'une propriété sur un document (forme aplatie, prête à afficher)."""

    prop_slug: str
    type: str
    # value : texte brut pour text/int/date/... ; None pour restricted_list.
    value: str | None = None
    # allowed_value_slug/label : renseignés pour restricted_list uniquement.
    allowed_value_slug: str | None = None
    allowed_value_label: str | None = None


class BlockObjectOut(BaseModel):
    id: str
    title: str
    functional_type_slug: str | None
    properties: list[PropertyValueBrief]


class BlockObjectsPage(BaseModel):
    """Page de documents d'un bloc avec leurs valeurs de propriétés."""

    block_slug: str
    page: int
    page_size: int
    total: int
    has_next: bool
    objects: list[BlockObjectOut]
