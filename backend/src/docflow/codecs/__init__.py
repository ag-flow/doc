"""Registre des codecs de type de contenu.

Ajouter un type de contenu = son fichier de codec + une entrée ici. Aucun
appelant ne change : la sauvegarde, la recherche et le calcul des références
passent tous par ``codec_for`` / ``codec_for_document``.

Un type absent du registre retombe sur le codec de repli (texte brut, aucun
lien) — jamais d'erreur, jamais de page cassée.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from docflow.codecs.base import ContentCodec, DocumentReferences
from docflow.codecs.markdown import MarkdownCodec
from docflow.codecs.plain import PlainTextCodec

__all__ = [
    "ContentCodec",
    "DocumentReferences",
    "FALLBACK",
    "REGISTRY",
    "codec_for",
    "codec_for_document",
]

#: Codecs instanciés une fois (ils sont sans état).
_MARKDOWN = MarkdownCodec()

#: Repli pour tout type inconnu du registre.
FALLBACK: ContentCodec[Any] = PlainTextCodec()

REGISTRY: dict[str, ContentCodec[Any]] = {
    _MARKDOWN.content_type: _MARKDOWN,
}


def codec_for(content_type: str | None) -> ContentCodec[Any]:
    """Codec servant ce type de contenu, ou le repli si le type est inconnu."""
    if content_type is None:
        return FALLBACK
    return REGISTRY.get(content_type, FALLBACK)


async def codec_for_document(
    conn: asyncpg.Connection,
    doc_id: uuid.UUID,
) -> ContentCodec[Any]:
    """Codec du document, résolu depuis `document.type`.

    À appeler dans la transaction du save : le type lu est celui sur lequel les
    références vont être reconstruites. Document introuvable → repli.
    """
    content_type = await conn.fetchval(
        "SELECT type FROM document WHERE doc_technical_key = $1", doc_id
    )
    return codec_for(content_type)
