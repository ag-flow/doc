from __future__ import annotations

from pydantic import BaseModel


class PropertyValueSet(BaseModel):
    """Écriture d'une valeur de propriété avec verrouillage optimiste.

    expected_version = 0  pour première écriture (aucune valeur existante).
    expected_version = n  pour mise à jour de la version n → n+1.
    """

    model_config = {"extra": "forbid"}

    value: str | None = None
    allowed_value_slug: str | None = None
    expected_version: int


class PropertyValueOut(BaseModel):
    prop_slug: str
    prop_label: str
    type: str
    version: int | None  # None si aucune valeur jamais définie
    value: str | None
    allowed_value_slug: str | None
    allowed_value_label: str | None
    required: bool
