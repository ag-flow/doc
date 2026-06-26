from __future__ import annotations

import pathlib

import pytest
import yaml

from docflow.templates.router import load_templates


def _write_yaml(path: pathlib.Path, data: object) -> None:
    with path.open("w") as f:
        yaml.dump(data, f, allow_unicode=True)


_VALID_TEMPLATE = {
    "version": 1,
    "template": "test-tpl",
    "label": "Template de test",
    "functional_types": [
        {"slug": "base", "abstract": True, "label": "Base"},
        {"slug": "epic", "label": "Epic", "inherit": "base"},
        {"slug": "story", "label": "Story", "inherit": "base", "parent": "epic"},
    ],
}


def test_load_templates_résumé_correct(tmp_path: pathlib.Path) -> None:
    _write_yaml(tmp_path / "test-tpl.yaml", _VALID_TEMPLATE)
    result = load_templates(tmp_path)
    assert len(result) == 1
    info = result[0]
    assert info.template == "test-tpl"
    assert info.label == "Template de test"
    assert info.version == 1
    assert info.path == "test-tpl.yaml"
    assert info.concrete_types == 2  # base exclu (abstract)
    assert set(info.type_slugs) == {"epic", "story"}


def test_load_templates_fichier_cassé_ignoré(tmp_path: pathlib.Path) -> None:
    (tmp_path / "good.yaml").write_text(
        yaml.dump(_VALID_TEMPLATE, allow_unicode=True)
    )
    (tmp_path / "broken.yaml").write_text("version: 1\n  invalid: yaml: [[[")
    result = load_templates(tmp_path)
    assert len(result) == 1
    assert result[0].template == "test-tpl"


def test_load_templates_yaml_invalide_ignoré(tmp_path: pathlib.Path) -> None:
    _write_yaml(tmp_path / "bad-schema.yaml", {"version": 1, "unexpected_key": True})
    result = load_templates(tmp_path)
    assert result == []


def test_load_templates_dossier_vide(tmp_path: pathlib.Path) -> None:
    result = load_templates(tmp_path)
    assert result == []


def test_load_templates_dossier_inexistant(tmp_path: pathlib.Path) -> None:
    result = load_templates(tmp_path / "nonexistent")
    assert result == []


def test_load_agile_basic_résumé() -> None:
    templates_dir = pathlib.Path(__file__).parent.parent.parent / "templates"
    result = load_templates(templates_dir)
    assert len(result) == 1
    info = result[0]
    assert info.template == "agile-basic"
    assert info.version == 1
    assert info.concrete_types == 4
    assert set(info.type_slugs) == {"epic", "feature", "story", "atdd"}
