"""La description de `expected_version` doit dire la vérité sur `set_property_value`.

Bug `77a21e59` : elle annonçait « 0 = désactivé, défaut » alors que `0` est la
valeur la PLUS STRICTE — elle signifie « j'attends qu'aucune valeur n'existe »
(`documents/service.py`, lignes 1425 et 1460 : `expected_version` est toujours
comparé, aucun chemin ne le désactive).

Un test sur une chaîne de documentation se justifie ici parce que cette chaîne
EST le contrat : c'est le seul élément sur lequel un agent décide comment appeler
l'outil. Une doc fausse ne casse aucun test de comportement et coûte un échec au
premier appel de chaque nouvel agent.
"""

from __future__ import annotations

from docflow.mcp.server import _TOOLS


def _expected_version_description(tool_name: str) -> str:
    tool = next(t for t in _TOOLS if t.name == tool_name)
    prop = tool.inputSchema["properties"]["expected_version"]
    return str(prop["description"])


def test_set_property_value_ne_promet_plus_un_defaut_desactive() -> None:
    """« 0 = désactivé » est faux : 0 exige qu'aucune valeur n'existe encore.

    L'assertion porte sur l'ÉQUIVALENCE fausse, pas sur le mot : une description
    juste emploie légitimement « jamais désactivée ». Interdire le vocabulaire
    plutôt que l'affirmation ferait échouer la bonne formulation — c'est l'erreur
    qu'a faite la première version de ce test.
    """
    description = _expected_version_description("set_property_value")

    assert "0 = désactivé" not in description


def test_set_property_value_enonce_la_semantique_reelle_de_zero() -> None:
    """Ne pas retirer le mensonge sans mettre la vérité à la place."""
    description = _expected_version_description("set_property_value")

    assert "0" in description
    # La description doit dire que la vérification a toujours lieu, et ce que
    # vaut 0 — sans quoi l'appelant ne sait toujours pas quoi envoyer.
    assert "aucune valeur" in description.lower()


def test_update_document_reste_la_reference_du_meme_contrat() -> None:
    """Les deux outils de la même surface doivent s'accorder sur la notion.

    `update_document` était déjà juste : sa description dit « OBLIGATOIRE ». Ce
    test gèle cet accord — si quelqu'un assouplit l'un, l'écart se voit.
    """
    description = _expected_version_description("update_document")

    assert "désactivé" not in description
    assert "OBLIGATOIRE" in description
