"""Import de template depuis un payload uploadé (POST /templates).

Installe un nouveau template global à partir d'un YAML natif uploadé — création
uniquement (409 si le slug est déjà installé), validation stricte du YAML, du
slug et de la cohérence de l'héritage.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from fastapi import HTTPException

import docflow.templates.router as tr

_TEMPLATE = {
    "version": 1,
    "template": "uploaded-tpl",
    "label": "Modèle uploadé",
    "functional_types": [
        {
            "slug": "base",
            "label": "Base",
            "abstract": True,
            "properties": [{"slug": "statut", "label": "Statut", "type": "text"}],
        },
        {
            "slug": "epic",
            "label": "Epic",
            "inherit": "base",
            "properties": [{"slug": "titre", "label": "Titre", "type": "text"}],
        },
    ],
}


@pytest.fixture()
def templates_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setattr(tr, "_TEMPLATES_DIR", tmp_path)
    return tmp_path


async def test_upload_installs_new_global_template(templates_dir: pathlib.Path) -> None:
    body = tr.TemplateUploadIn(yaml_content=yaml.dump(_TEMPLATE, allow_unicode=True))
    info = await tr.create_template_from_upload(body)

    assert info.template == "uploaded-tpl"
    assert info.version == 1
    # Le type abstract est exclu du décompte concret.
    assert info.concrete_types == 1
    assert info.type_slugs == ["epic"]
    # Persisté dans le répertoire global → importable ensuite.
    assert (templates_dir / "uploaded-tpl.yaml").exists()


async def test_upload_conflict_when_slug_installed(templates_dir: pathlib.Path) -> None:
    (templates_dir / "uploaded-tpl.yaml").write_text(yaml.dump(_TEMPLATE, allow_unicode=True))
    body = tr.TemplateUploadIn(yaml_content=yaml.dump(_TEMPLATE, allow_unicode=True))
    with pytest.raises(HTTPException) as exc:
        await tr.create_template_from_upload(body)
    assert exc.value.status_code == 409


async def test_upload_invalid_yaml_422(templates_dir: pathlib.Path) -> None:
    # Mapping valide en YAML mais invalide comme Template (champs requis absents).
    body = tr.TemplateUploadIn(yaml_content="foo: bar")
    with pytest.raises(HTTPException) as exc:
        await tr.create_template_from_upload(body)
    assert exc.value.status_code == 422


async def test_upload_incoherent_inheritance_422(templates_dir: pathlib.Path) -> None:
    bad = {
        "version": 1,
        "template": "bad-tpl",
        "label": "Bad",
        "functional_types": [
            {"slug": "epic", "label": "Epic", "inherit": "ghost", "properties": []},
        ],
    }
    body = tr.TemplateUploadIn(yaml_content=yaml.dump(bad, allow_unicode=True))
    with pytest.raises(HTTPException) as exc:
        await tr.create_template_from_upload(body)
    assert exc.value.status_code == 422


async def test_upload_invalid_slug_422(templates_dir: pathlib.Path) -> None:
    bad = {
        "version": 1,
        "template": "Bad_Slug",
        "label": "Bad",
        "functional_types": [{"slug": "epic", "label": "Epic", "properties": []}],
    }
    body = tr.TemplateUploadIn(yaml_content=yaml.dump(bad, allow_unicode=True))
    with pytest.raises(HTTPException) as exc:
        await tr.create_template_from_upload(body)
    assert exc.value.status_code == 422
