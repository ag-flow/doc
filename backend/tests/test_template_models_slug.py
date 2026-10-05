"""Les slugs d'un Template (type, propriété, valeur autorisée) doivent
respecter le même format que la validation REST (`validate_slug`) — sinon un
template YAML importable directement contourne la regex appliquée partout
ailleurs (`schemas/types.py`, `schemas/properties.py`)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from docflow.templates.models import AllowedValueDef, PropDef, Template, TypeDef

_BASE_TEMPLATE: dict[str, object] = {
    "version": 1,
    "template": "tpl-slug",
    "label": "Template",
    "functional_types": [{"slug": "epic", "label": "Epic"}],
}


@pytest.mark.parametrize("bad_slug", ["Epic", "epic type", "epic/type", ""])
def test_template_type_slug_invalid_rejected(bad_slug: str) -> None:
    payload = {
        **_BASE_TEMPLATE,
        "functional_types": [{"slug": bad_slug, "label": "Bad"}],
    }
    with pytest.raises(ValidationError):
        Template.model_validate(payload)


def test_type_def_slug_invalid_rejected_directly() -> None:
    with pytest.raises(ValidationError):
        TypeDef(slug="Bad/Slug", label="Bad")


@pytest.mark.parametrize("bad_slug", ["Statut", "sta tut", "sta/tut"])
def test_template_property_slug_invalid_rejected(bad_slug: str) -> None:
    payload = {
        **_BASE_TEMPLATE,
        "functional_types": [
            {
                "slug": "epic",
                "label": "Epic",
                "properties": [{"slug": bad_slug, "label": "Bad", "type": "text"}],
            }
        ],
    }
    with pytest.raises(ValidationError):
        Template.model_validate(payload)


def test_prop_def_slug_invalid_rejected_directly() -> None:
    with pytest.raises(ValidationError):
        PropDef(slug="Bad Slug", label="Bad", type="text")


@pytest.mark.parametrize("bad_slug", ["Todo", "to do", "to/do"])
def test_template_allowed_value_slug_invalid_rejected(bad_slug: str) -> None:
    payload = {
        **_BASE_TEMPLATE,
        "functional_types": [
            {
                "slug": "epic",
                "label": "Epic",
                "properties": [
                    {
                        "slug": "statut",
                        "label": "Statut",
                        "type": "restricted_list",
                        "allowed_values": [{"slug": bad_slug, "label": "Bad"}],
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValidationError):
        Template.model_validate(payload)


def test_allowed_value_def_slug_invalid_rejected_directly() -> None:
    with pytest.raises(ValidationError):
        AllowedValueDef(slug="Bad/Slug", label="Bad")


def test_template_valid_slugs_accepted() -> None:
    payload = {
        **_BASE_TEMPLATE,
        "functional_types": [
            {
                "slug": "epic",
                "label": "Epic",
                "properties": [
                    {
                        "slug": "statut",
                        "label": "Statut",
                        "type": "restricted_list",
                        "allowed_values": [{"slug": "todo", "label": "À faire"}],
                    }
                ],
            }
        ],
    }
    tpl = Template.model_validate(payload)
    assert tpl.functional_types[0].slug == "epic"
