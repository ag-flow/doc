"""Codec `model-layout` — la présentation d'un modèle de données (épic MLD — F7)."""

from __future__ import annotations

import pytest

from docflow.codecs import codec_for
from docflow.codecs.model_layout import ModelLayoutCodec

CODEC = ModelLayoutCodec()

LAYOUT = """
schemaVersion: 1
viewport:
  x: 0
  y: 0
  zoom: 1
entities:
  - id: doc-commande
    x: 10
    y: 20
    collapsed: false
relations:
  - id: rel_cccccccccccc
    waypoints:
      - x: 150
        y: 90
"""


def _codes(content: str | None) -> list[str]:
    return [e.code for e in CODEC.validate(content)]


def test_le_codec_est_servi_par_le_registre() -> None:
    assert isinstance(codec_for("model-layout"), ModelLayoutCodec)


# ── Projection texte : vide à dessein ────────────────────────────────────────


def test_la_projection_texte_est_vide() -> None:
    """Des coordonnées ne veulent rien dire pour quelqu'un qui cherche.

    Le sens du modèle vit dans les entités enfants, indexées chacune de leur
    côté : le remonter ici le dupliquerait et polluerait les résultats.
    """
    assert CODEC.to_plain_text(LAYOUT) == ""
    assert CODEC.to_plain_text(None) == ""


def test_aucune_reference_sortante() -> None:
    refs = CODEC.references(LAYOUT)
    assert refs.documents == {} and refs.artifacts == set() and refs.datasets == []


# ── Validation ───────────────────────────────────────────────────────────────


def test_une_mise_en_page_valide_ne_produit_aucune_erreur() -> None:
    assert CODEC.validate(LAYOUT) == []


@pytest.mark.parametrize("vide", [None, "", "   \n"])
def test_un_modele_sans_mise_en_page_est_valide(vide: str | None) -> None:
    """Un modèle qui vient de naître n'a pas encore de mise en page : c'est normal."""
    assert CODEC.validate(vide) == []


def test_un_yaml_casse_est_refuse() -> None:
    assert _codes("entities: [oups\n") == ["content_unparseable"]


def test_une_entree_sans_identifiant_est_refusee() -> None:
    assert "missing_id" in _codes("entities:\n  - x: 10\n    y: 20\n")


def test_une_entree_dupliquee_est_refusee() -> None:
    contenu = "entities:\n  - id: a\n    x: 0\n    y: 0\n  - id: a\n    x: 1\n    y: 1\n"
    assert "duplicate_id" in _codes(contenu)


def test_une_coordonnee_non_numerique_est_refusee() -> None:
    assert "invalid_number" in _codes("entities:\n  - id: a\n    x: gauche\n")


def test_un_booleen_n_est_pas_une_coordonnee() -> None:
    # En Python `True` est un `int` : sans garde explicite, il passerait.
    assert "invalid_number" in _codes("entities:\n  - id: a\n    x: true\n")


def test_toutes_les_erreurs_sont_remontees_ensemble() -> None:
    contenu = "entities:\n  - x: 1\n  - id: b\n    y: haut\n"
    assert {"missing_id", "invalid_number"} <= set(_codes(contenu))


# ── Canonicalisation ─────────────────────────────────────────────────────────


def test_l_ordre_des_cles_est_fige() -> None:
    desordre = "entities:\n  - y: 2\n    id: a\n    x: 1\nschemaVersion: 1\n"
    canonical = CODEC.canonicalize(desordre)
    layout = CODEC.parse(canonical)

    assert list(layout) == ["schemaVersion", "entities"]
    assert list(layout["entities"][0]) == ["id", "x", "y"]


def test_la_canonicalisation_est_idempotente() -> None:
    once = CODEC.canonicalize(LAYOUT)
    assert CODEC.canonicalize(once) == once


def test_la_version_de_schema_est_posee_si_absente() -> None:
    layout = CODEC.parse(CODEC.canonicalize("entities:\n  - id: a\n    x: 0\n    y: 0\n"))
    assert layout["schemaVersion"] == 1


def test_les_cles_inconnues_survivent() -> None:
    """Ne pas comprendre une clé n'autorise pas à détruire le travail."""
    contenu = "x-maison: garde-moi\nentities:\n  - id: a\n    x: 0\n    y: 0\n"
    assert CODEC.parse(CODEC.canonicalize(contenu))["x-maison"] == "garde-moi"


def test_canonicalize_ne_detruit_jamais_un_contenu_illisible() -> None:
    casse = "entities: [oups\n"
    assert CODEC.canonicalize(casse) == casse
