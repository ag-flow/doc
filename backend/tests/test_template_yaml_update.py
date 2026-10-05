"""PUT /templates/{slug}/yaml doit valider l'héritage AVANT d'écrire le fichier.

Régression : le fichier était écrasé par un YAML dont l'héritage était
incohérent (cycle, ou `inherit` vers un slug absent) AVANT que `resolve()` ne
lève — 500 non géré, et le template disparaissait ensuite du listing
(`load_templates` avale l'exception silencieusement)."""

from __future__ import annotations

import pathlib

import pytest
import yaml
from fastapi import HTTPException

import docflow.templates.router as tr
from docflow.templates.router import TemplateYamlBody

_TEMPLATE = {
    "version": 1,
    "template": "my-tpl",
    "label": "Mon modèle",
    "functional_types": [
        {"slug": "epic", "label": "Epic"},
    ],
}

_CYCLIC_TEMPLATE = {
    "version": 2,
    "template": "my-tpl",
    "label": "Mon modèle",
    "functional_types": [
        {"slug": "epic", "label": "Epic", "inherit": "feature"},
        {"slug": "feature", "label": "Feature", "inherit": "epic"},
    ],
}


@pytest.fixture()
def templates_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    (tmp_path / "my-tpl.yaml").write_text(yaml.dump(_TEMPLATE, allow_unicode=True))
    monkeypatch.setattr(tr, "_TEMPLATES_DIR", tmp_path)
    return tmp_path


async def test_update_yaml_cyclic_inheritance_rejected_and_file_untouched(
    templates_dir: pathlib.Path,
) -> None:
    yaml_file = templates_dir / "my-tpl.yaml"
    original_content = yaml_file.read_text()

    body = TemplateYamlBody(yaml_content=yaml.dump(_CYCLIC_TEMPLATE, allow_unicode=True))
    with pytest.raises(HTTPException) as exc:
        await tr.update_template_yaml("my-tpl", body)
    assert exc.value.status_code == 422

    # Le fichier original n'a PAS été écrasé par le YAML cassé.
    assert yaml_file.read_text() == original_content
    # Le template reste résolvable/listable (pas avalé silencieusement).
    listed = tr.load_templates(templates_dir)
    assert [t.template for t in listed] == ["my-tpl"]
    assert listed[0].version == 1
