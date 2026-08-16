"""F1 — Export aplati d'un template (GET /templates/{slug}/export).

L'export résout l'héritage : les types `abstract` disparaissent, les types
concrets portent toutes leurs propriétés (héritées + propres), JSON téléchargeable.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from fastapi import HTTPException

import docflow.templates.router as tr

_TEMPLATE = {
    "version": 3,
    "template": "my-tpl",
    "label": "Mon modèle",
    "functional_types": [
        {
            "slug": "base",
            "label": "Base",
            "abstract": True,
            "properties": [
                {
                    "slug": "statut",
                    "label": "Statut",
                    "type": "restricted_list",
                    "required": True,
                    "allowed_values": [{"slug": "todo", "label": "À faire"}],
                }
            ],
        },
        {
            "slug": "epic",
            "label": "Epic",
            "inherit": "base",
            "content_template": "# {{title}}\n\n## Contexte",
            "properties": [{"slug": "titre", "label": "Titre", "type": "text"}],
        },
    ],
}


@pytest.fixture()
def templates_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    (tmp_path / "my-tpl.yaml").write_text(yaml.dump(_TEMPLATE, allow_unicode=True))
    monkeypatch.setattr(tr, "_TEMPLATES_DIR", tmp_path)
    return tmp_path


async def test_export_flattens_inheritance_and_downloads(templates_dir: pathlib.Path) -> None:
    resp = await tr.export_template("my-tpl")

    # Téléchargement JSON nommé d'après le slug.
    assert resp.media_type == "application/json"
    assert resp.headers["content-disposition"] == 'attachment; filename="my-tpl.json"'

    payload = json.loads(bytes(resp.body))
    assert payload["template"] == "my-tpl"
    assert payload["label"] == "Mon modèle"
    assert payload["version"] == 3

    types = {t["slug"]: t for t in payload["functional_types"]}
    # Le type abstract est EXCLU ; seul le concret reste.
    assert set(types) == {"epic"}
    epic = types["epic"]
    assert epic["parent"] is None
    prop_slugs = [p["slug"] for p in epic["properties"]]
    # Propriété héritée (statut) + propre (titre), toutes aplaties sur le type.
    assert "statut" in prop_slugs and "titre" in prop_slugs
    statut = next(p for p in epic["properties"] if p["slug"] == "statut")
    assert statut["required"] is True
    assert [av["slug"] for av in statut["allowed_values"]] == ["todo"]


async def test_export_includes_content_template(templates_dir: pathlib.Path) -> None:
    resp = await tr.export_template("my-tpl")
    payload = json.loads(bytes(resp.body))
    epic = next(t for t in payload["functional_types"] if t["slug"] == "epic")
    assert epic["content_template"] == "# {{title}}\n\n## Contexte"


async def test_export_unknown_template_404(templates_dir: pathlib.Path) -> None:
    with pytest.raises(HTTPException) as exc:
        await tr.export_template("inconnu")
    assert exc.value.status_code == 404
