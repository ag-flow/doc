"""Tests de la substitution JSON-safe des variables d'automates."""

from __future__ import annotations

import json

import pytest

from docflow.automations.substitution import (
    render_and_validate,
    render_body,
    unresolved_variables,
)


def test_simple_substitution() -> None:
    tpl = '{"path": "{id_document}", "title": "{title}"}'
    result = render_body(tpl, {"id_document": "abc-123", "title": "Hello"})
    assert result == '{"path": "abc-123", "title": "Hello"}'


def test_content_with_quotes_produces_valid_json() -> None:
    """Un contenu avec guillemets ne doit pas casser le JSON."""
    tpl = '{"path": "{id_document}", "content": "{content}", "title": "{title}"}'
    variables = {
        "id_document": "uuid-1",
        "content": 'Line 1\nLine with "quotes" inside',
        "title": "My doc",
    }
    rendered = render_and_validate(tpl, variables)
    assert rendered is not None, "Le rendu doit être du JSON valide"
    parsed = json.loads(rendered)
    assert parsed["content"] == 'Line 1\nLine with "quotes" inside'
    assert parsed["path"] == "uuid-1"


def test_content_with_backslash_produces_valid_json() -> None:
    tpl = '{"content": "{content}"}'
    variables = {"content": "path\\to\\file"}
    rendered = render_and_validate(tpl, variables)
    assert rendered is not None
    assert json.loads(rendered)["content"] == "path\\to\\file"


def test_content_with_newline_produces_valid_json() -> None:
    tpl = '{"content": "{content}"}'
    variables = {"content": "line1\nline2\nline3"}
    rendered = render_and_validate(tpl, variables)
    assert rendered is not None
    assert json.loads(rendered)["content"] == "line1\nline2\nline3"


def test_invalid_template_returns_none() -> None:
    """Un template mal formé (variable hors chaîne JSON) retourne None."""
    tpl = '{"value": {id_document}}'  # variable sans guillemets = JSON invalide
    result = render_and_validate(tpl, {"id_document": "abc"})
    # "abc" n'est pas un token JSON valide à cette position
    assert result is None


def test_empty_variables() -> None:
    tpl = '{"key": "value"}'
    rendered = render_and_validate(tpl, {})
    assert rendered is not None
    assert json.loads(rendered) == {"key": "value"}


def test_unicode_content() -> None:
    tpl = '{"content": "{content}"}'
    variables = {"content": "Héllo wörld 🦋"}
    rendered = render_and_validate(tpl, variables)
    assert rendered is not None
    assert json.loads(rendered)["content"] == "Héllo wörld 🦋"


@pytest.mark.parametrize(
    "content",
    [
        'say "hello"',
        "tab\there",
        "cr\rhere",
        "null\x00byte",
        "back\\slash",
        'mix\n"of"\nthings',
    ],
)
def test_various_special_chars(content: str) -> None:
    tpl = '{"content": "{content}"}'
    rendered = render_and_validate(tpl, {"content": content})
    assert rendered is not None, f"Doit être valide pour : {content!r}"
    assert json.loads(rendered)["content"] == content


# ── Détection des variables non résolues (fail-loud, cf. bug indexation) ──────


def test_unresolved_variables_detecte_placeholder_manquant() -> None:
    tpl = '{"bloc": "{event.blockSlug}", "type": "{event.functionalTypeSlug}"}'
    missing = unresolved_variables(tpl, {"event.code": "updated.v1"})
    assert missing == ["event.blockSlug", "event.functionalTypeSlug"]


def test_unresolved_variables_vide_quand_tout_est_fourni() -> None:
    tpl = '{"bloc": "{event.blockSlug}", "doc": "{id_document}"}'
    assert unresolved_variables(tpl, {"event.blockSlug": "epics", "id_document": "x"}) == []


def test_unresolved_variables_ignore_les_accolades_json_de_structure() -> None:
    """Les accolades de structure JSON ne sont pas des placeholders."""
    tpl = '{"payload": {"nested": "{id_document}"}, "empty": {}}'
    assert unresolved_variables(tpl, {"id_document": "x"}) == []


def test_unresolved_variables_ne_scanne_pas_les_valeurs_substituees() -> None:
    """Un contenu qui contient des accolades ne doit pas être pris pour un
    placeholder : la détection porte sur le GABARIT, pas sur le rendu."""
    tpl = '{"content": "{content}"}'
    variables = {"content": "exemple de gabarit littéral : {event.blockSlug}"}
    # `content` est fourni → aucun placeholder non résolu dans le gabarit.
    assert unresolved_variables(tpl, variables) == []
    rendered = render_and_validate(tpl, variables)
    assert rendered is not None
    assert json.loads(rendered)["content"] == "exemple de gabarit littéral : {event.blockSlug}"
