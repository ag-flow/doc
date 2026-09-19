"""Codec `table-schema` : grammaire, canonicalisation, validation (épic MLD — F5)."""

from __future__ import annotations

import pytest

from docflow.codecs import codec_for
from docflow.codecs.table_schema import TableSchemaCodec, grammar, ids

CODEC = TableSchemaCodec()

VALID = """
name: commande
title: Commande client
description: Une commande passée par un client.
fields:
  - name: id
    type: uuid
    description: Identifiant de la commande.
  - name: montant_ttc
    type: number
    title: Montant TTC
primaryKey: id
docflow.relations:
  - name: passee_par
    title: Passée par
    cardinality: many-to-one
    from: id
    to:
      resource: client
      fields: id
"""


def _errors(content: str) -> dict[str, str]:
    """{path: code} — rend les assertions lisibles."""
    return {e.path: e.code for e in CODEC.validate(content)}


# ── Registre ──────────────────────────────────────────────────────────────────


def test_le_codec_est_servi_par_le_registre() -> None:
    assert isinstance(codec_for("table-schema"), TableSchemaCodec)


def test_le_codec_sait_lire_les_references() -> None:
    """Sans quoi la réconciliation purgerait les références (garde-fou F3)."""
    assert CODEC.extracts_references is True


# ── Validation : cas nominal ──────────────────────────────────────────────────


def test_un_schema_valide_ne_produit_aucune_erreur() -> None:
    assert CODEC.validate(VALID) == []


# ── Validation : types logiques, jamais physiques ────────────────────────────


@pytest.mark.parametrize(
    ("physique", "attendu"),
    [("varchar(255)", "string"), ("int", "integer"), ("timestamptz", "datetime"),
     ("numeric(10,2)", "number"), ("bool", "boolean"), ("jsonb", "object")],
)
def test_un_type_physique_est_refuse_avec_son_equivalent_logique(
    physique: str, attendu: str
) -> None:
    """Le refus doit ENSEIGNER la règle, pas seulement la constater."""
    content = f"name: t\nfields:\n  - name: c\n    type: {physique}\n"
    errors = CODEC.validate(content)

    assert len(errors) == 1
    err = errors[0]
    assert err.code == "physical_type"
    assert err.path == "fields[0].type"
    assert attendu in err.message
    assert err.allowed == grammar.FIELD_TYPES
    assert err.doc == grammar.GRAMMAR_DOC


def test_un_type_inconnu_liste_le_vocabulaire_accepte() -> None:
    errors = CODEC.validate("name: t\nfields:\n  - name: c\n    type: licorne\n")
    assert [e.code for e in errors] == ["unknown_type"]
    assert "string" in errors[0].allowed


# ── Validation : toutes les erreurs d'un coup ────────────────────────────────


def test_toutes_les_erreurs_sont_remontees_ensemble() -> None:
    """Un appelant doit pouvoir corriger en une passe, pas une erreur à la fois."""
    content = """
name: 1_mauvais
fields:
  - name: ok
    type: string
  - name: ok
    type: licorne
  - type: string
"""
    errors = _errors(content)

    assert errors["name"] == "invalid_name"
    assert errors["fields[1].name"] == "duplicate_name"
    assert errors["fields[1].type"] == "unknown_type"
    assert errors["fields[2].name"] == "missing_name"
    assert len(errors) >= 4


def test_le_chemin_designe_l_entree_fautive() -> None:
    content = "name: t\nfields:\n  - name: a\n    type: string\n  - name: b\n    type: zzz\n"
    assert "fields[1].type" in _errors(content)


# ── Validation : cohérence interne ───────────────────────────────────────────


def test_primary_key_doit_designer_un_champ_declare() -> None:
    content = "name: t\nfields:\n  - name: a\n    type: string\nprimaryKey: absent\n"
    errors = CODEC.validate(content)
    assert errors[0].code == "unknown_field_ref"
    assert errors[0].allowed == ("a",)


def test_une_relation_doit_partir_d_un_champ_declare() -> None:
    content = """
name: t
fields:
  - name: a
    type: string
docflow.relations:
  - name: r
    cardinality: many-to-one
    from: fantome
    to:
      resource: autre
      fields: id
"""
    assert _errors(content)["docflow.relations[0].from[0]"] == "unknown_field_ref"


def test_une_cardinalite_inconnue_est_refusee() -> None:
    content = """
name: t
fields:
  - name: a
    type: string
docflow.relations:
  - name: r
    cardinality: plusieurs-vers-plusieurs
    from: a
    to:
      resource: autre
      fields: id
"""
    errors = CODEC.validate(content)
    assert errors[0].code == "unknown_cardinality"
    assert "many-to-many" in errors[0].allowed


def test_la_cible_d_une_relation_n_est_pas_verifiee_localement() -> None:
    """Les champs de la table CIBLE vivent dans un autre document : hors de portée."""
    assert CODEC.validate(VALID) == []


# ── Validation : contenu illisible ───────────────────────────────────────────


def test_un_yaml_casse_donne_content_unparseable() -> None:
    errors = CODEC.validate("name: t\n  fields: [oups\n")
    assert errors[0].code == "content_unparseable"
    assert errors[0].doc == grammar.GRAMMAR_DOC


@pytest.mark.parametrize("vide", [None, "", "   \n"])
def test_un_contenu_vide_est_refuse(vide: str | None) -> None:
    assert [e.code for e in CODEC.validate(vide)] == ["empty_content"]


# ── Canonicalisation ─────────────────────────────────────────────────────────


def test_la_canonicalisation_alloue_les_identifiants_manquants() -> None:
    canonical = CODEC.canonicalize(VALID)
    schema = CODEC.parse(canonical)

    for field in schema["fields"]:
        assert ids.is_valid(field[grammar.ID_KEY])
        assert field[grammar.ID_KEY].startswith(ids.FIELD_PREFIX)
    for rel in schema[grammar.RELATIONS_KEY]:
        assert rel[grammar.ID_KEY].startswith(ids.RELATION_PREFIX)


def test_les_identifiants_deja_presents_sont_conserves() -> None:
    """L'identité d'un champ ne doit pas bouger : sinon tout ce qui s'y accroche se détache."""
    first = CODEC.canonicalize(VALID)
    kept = CODEC.parse(first)["fields"][0][grammar.ID_KEY]

    again = CODEC.parse(CODEC.canonicalize(first))
    assert again["fields"][0][grammar.ID_KEY] == kept


def test_les_identifiants_ne_sont_jamais_recycles() -> None:
    """Supprimer un champ puis en ajouter un autre ne doit pas réattribuer son id."""
    canonical = CODEC.canonicalize(VALID)
    schema = CODEC.parse(canonical)
    retire = schema["fields"].pop(0)[grammar.ID_KEY]
    schema["fields"].append({"name": "nouveau", "type": "string"})

    reprise = CODEC.parse(CODEC.serialize(schema))
    assert retire not in {f[grammar.ID_KEY] for f in reprise["fields"]}


def test_la_canonicalisation_est_idempotente() -> None:
    once = CODEC.canonicalize(VALID)
    assert CODEC.canonicalize(once) == once


def test_l_ordre_des_cles_est_fige() -> None:
    """Deux documents de même sens s'écrivent pareil — sinon les diffs sont illisibles."""
    desordre = """
fields:
  - type: string
    name: a
description: D
name: t
"""
    schema = CODEC.parse(CODEC.canonicalize(desordre))
    assert list(schema) == ["name", "description", "fields"]
    assert list(schema["fields"][0])[:3] == [grammar.ID_KEY, "name", "type"]


def test_les_cles_inconnues_survivent_a_l_aller_retour() -> None:
    """Ne pas comprendre une clé n'autorise pas à détruire le travail de l'utilisateur."""
    content = "name: t\nx-maison: garde-moi\nfields:\n  - name: a\n    type: string\n"
    assert CODEC.parse(CODEC.canonicalize(content))["x-maison"] == "garde-moi"


def test_yaml_1_2_ne_transforme_pas_no_en_booleen() -> None:
    """En YAML 1.1 (PyYAML), un champ nommé `no` deviendrait False."""
    schema = CODEC.parse(CODEC.canonicalize("name: t\nfields:\n  - name: no\n    type: string\n"))
    assert schema["fields"][0]["name"] == "no"


# ── Projection texte ─────────────────────────────────────────────────────────


def test_to_plain_text_rend_le_sens_pas_la_syntaxe() -> None:
    text = CODEC.to_plain_text(VALID)

    assert "Commande client" in text
    assert "Une commande passée par un client." in text
    assert "Identifiant de la commande." in text
    assert "Montant TTC" in text
    # Les mots-clés de la grammaire ne doivent pas polluer la recherche.
    assert "cardinality" not in text
    assert "docflow.relations" not in text
    assert "primaryKey" not in text


def test_to_plain_text_d_un_contenu_illisible_renvoie_le_brut() -> None:
    """Un document abîmé doit rester trouvable, pas devenir invisible."""
    casse = "name: t\n  fields: [oups\n"
    assert CODEC.to_plain_text(casse) == casse.strip()


# ── Références ───────────────────────────────────────────────────────────────


def test_les_references_documentaires_sont_extraites() -> None:
    doc_id = "550e8400-e29b-41d4-a716-446655440000"
    content = (
        f"name: t\ndescription: voir docflow://doc/{doc_id}\n"
        "fields:\n  - name: a\n    type: string\n"
    )
    refs = CODEC.references(content)

    assert refs.documents == {doc_id: ""}
    # Cette grammaire ne porte ni artefact ni dataset : vide est EXACT ici.
    assert refs.artifacts == set()
    assert refs.datasets == []


def test_canonicalize_ne_detruit_jamais_un_contenu_illisible() -> None:
    """Sur le chemin de sauvegarde, perdre du texte utilisateur est pire que
    le garder mal formé. Le refus appartient à `validate`, pas ici."""
    casse = "name: t\n  fields: [oups\n"
    assert CODEC.canonicalize(casse) == casse
    assert CODEC.canonicalize("") == ""
    assert CODEC.canonicalize(None) == ""


def test_parse_ne_leve_jamais_sur_un_contenu_casse() -> None:
    """Chemin de lecture : un contenu abîmé ne doit pas casser une sauvegarde."""
    assert CODEC.parse("name: t\n  fields: [oups\n") == {}
    assert CODEC.parse(None) == {}
