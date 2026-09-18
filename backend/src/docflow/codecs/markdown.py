"""Codec du type de contenu `md` — première implémentation du contrat.

Le stockage EST la forme d'édition (markdown brut) : ``parse``/``serialize``
sont l'identité. Le travail réel du codec porte sur les deux projections :

- ``references`` délègue aux extracteurs historiques, inchangés — la bascule sur
  le contrat est donc sans changement de comportement pour l'existant ;
- ``to_plain_text`` retire la syntaxe pour ne garder que le texte lisible.
"""

from __future__ import annotations

import re

from docflow.artifacts.parser import extract_artifact_ids
from docflow.codecs.base import ContentCodec, DocumentReferences
from docflow.datasets.parser import extract_dataset_ids
from docflow.documents import content_types
from docflow.references.parser import extract_references

# Blocs clôturés : on retire les lignes de clôture et on GARDE le corps (le
# contenu d'un bloc `df-*` ou d'un extrait de code est du texte cherchable).
_FENCE_LINE = re.compile(r"^[ \t]*(?:```|~~~).*$", re.MULTILINE)
# Image AVANT lien : `![alt](url)` contient `[alt](url)`.
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
_QUOTE = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)
_BULLET = re.compile(r"^[ \t]*(?:[-*+]|\d+\.)[ \t]+", re.MULTILINE)
_TABLE_SEP = re.compile(r"^[ \t]*\|?[ \t:|-]{3,}\|?[ \t]*$", re.MULTILINE)
# Marqueurs d'emphase appariés. L'underscore simple exige des frontières de mot :
# `snake_case` ne doit pas être mutilé (un identifiant reste cherchable).
_STRONG = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_STRONG_U = re.compile(r"__(.+?)__", re.DOTALL)
_STRIKE = re.compile(r"~~(.+?)~~", re.DOTALL)
_EM = re.compile(r"\*(.+?)\*", re.DOTALL)
_EM_U = re.compile(r"(?<![\w_])_([^_\n]+?)_(?![\w_])")
_CODE = re.compile(r"`([^`\n]+?)`")
_BLANK_RUN = re.compile(r"\n{3,}")


class MarkdownCodec(ContentCodec[str]):
    """Codec `md`. Le modèle canonique est le markdown lui-même."""

    content_type = content_types.DEFAULT

    def parse(self, content: str | None) -> str:
        return content or ""

    def serialize(self, model: str) -> str:
        return model

    def to_plain_text(self, content: str | None) -> str:
        """Markdown → texte lisible (recherche, RAG).

        Retire la syntaxe et garde le texte : libellés de liens et d'images,
        corps des blocs clôturés, texte des titres et des listes.
        """
        if not content:
            return ""
        text = _FENCE_LINE.sub("", content)
        text = _IMAGE.sub(r"\1", text)
        text = _LINK.sub(r"\1", text)
        text = _HEADING.sub("", text)
        text = _QUOTE.sub("", text)
        text = _BULLET.sub("", text)
        text = _TABLE_SEP.sub("", text)
        text = _STRONG.sub(r"\1", text)
        text = _STRONG_U.sub(r"\1", text)
        text = _STRIKE.sub(r"\1", text)
        text = _EM.sub(r"\1", text)
        text = _EM_U.sub(r"\1", text)
        text = _CODE.sub(r"\1", text)
        return _BLANK_RUN.sub("\n\n", text).strip()

    def references(self, content: str | None) -> DocumentReferences:
        """Liens sortants du markdown — délégation aux extracteurs historiques."""
        raw = content or ""
        return DocumentReferences(
            documents=extract_references(raw),
            artifacts=extract_artifact_ids(raw),
            datasets=extract_dataset_ids(content),
        )
