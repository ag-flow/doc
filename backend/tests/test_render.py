"""Port de rendu HTML→PNG : résolution de la largeur de cadre."""

from __future__ import annotations

from docflow.artifacts import render


def test_resolve_width_explicit_wins() -> None:
    # Largeur explicite prime sur le preset viewport, et est bornée.
    assert render.resolve_width("mobile", 360) == 360
    assert render.resolve_width(None, 99999) == 4096


def test_resolve_width_viewport_presets() -> None:
    assert render.resolve_width("mobile", None) == 390
    assert render.resolve_width("tablette", None) == 768
    assert render.resolve_width("tablet", None) == 768
    assert render.resolve_width("desktop", None) == 1024


def test_resolve_width_defaults_to_desktop() -> None:
    assert render.resolve_width(None, None) == 1024
    assert render.resolve_width("inconnu", None) == 1024
    assert render.resolve_width("", 0) == 1024
