"""Lecture / écriture YAML canonique du `table-schema` (épic MLD — F5).

YAML **1.2** via ruamel : PyYAML implémente 1.1, où `no`, `on` et `y` sont des
booléens. Un champ nommé `no` deviendrait `False` — inacceptable pour une
grammaire qui décrit des noms de colonnes.

**Canonique** : ordre de clés figé (cf. `grammar`), indentation constante,
quotage explicite. Deux documents de même sens produisent le même texte, octet
pour octet — c'est ce qui rend le versionnement et les diffs exploitables.

**Les commentaires ne sont pas préservés** — assumé par le cadrage. La
canonicalisation réécrit le document à partir de sa structure ; garder les
commentaires supposerait de savoir à quel nœud les rattacher après réordonnancement.
La description d'un champ (`description:`) est le bon endroit pour un commentaire.
"""

from __future__ import annotations

import io
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

_INDENT_MAPPING = 2
_INDENT_SEQUENCE = 4
_SEQUENCE_DASH_OFFSET = 2
#: Assez large pour ne pas replier les descriptions au milieu d'une phrase.
_LINE_WIDTH = 120


def _engine() -> YAML:
    yaml = YAML(typ="rt")  # round-trip : conserve la forme des scalaires
    yaml.version = (1, 2)
    yaml.indent(mapping=_INDENT_MAPPING, sequence=_INDENT_SEQUENCE, offset=_SEQUENCE_DASH_OFFSET)
    yaml.width = _LINE_WIDTH
    # Ne pas replier les chaînes longues sur plusieurs lignes : un diff de
    # description resterait sinon illisible.
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    return yaml


class YamlSyntaxError(Exception):
    """Le contenu n'est pas du YAML lisible — distinct d'un YAML valide mais mal formé."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def load(content: str | None) -> Any:
    """Contenu → structure Python. Lève `YamlSyntaxError` si illisible.

    Le refus est réservé au chemin d'écriture ; les appelants de lecture
    (`to_plain_text`, `references`) rattrapent l'exception.
    """
    if not content or not content.strip():
        return None
    try:
        return _engine().load(content)
    except YAMLError as exc:
        raise YamlSyntaxError(str(exc).strip()) from exc


def dump(data: Any) -> str:
    """Structure Python → YAML canonique."""
    if data is None:
        return ""
    stream = io.StringIO()
    _engine().dump(data, stream)
    text = stream.getvalue()
    # ruamel émet la directive `%YAML 1.2` + `---` dès que `version` est posée.
    # Elle est exacte mais bruyante en tête de chaque document : on la retire,
    # la version reste imposée à la LECTURE, qui est ce qui compte.
    lines = text.splitlines()
    while lines and (lines[0].startswith("%YAML") or lines[0] == "---"):
        lines.pop(0)
    return "\n".join(lines).strip() + "\n"
