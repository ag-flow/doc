"""Écriture d'une révision de document (épic MLD — F3b).

Point de passage UNIQUE vers `document_version` : toute révision est écrite avec
sa projection texte, calculée par le codec du type de contenu du document.

Même principe qu'en F3 pour les références : un seul endroit connaît le codec,
les appelants n'en savent rien. Un nouveau type de contenu devient cherchable
« par son sens » sans qu'aucun site de sauvegarde ne change.
"""

from __future__ import annotations

import uuid

import asyncpg

from docflow.codecs import codec_for_document

_INSERT_SQL = """
INSERT INTO document_version (document_ref, version_number, title, content, plain_text)
VALUES ($1, $2, $3, $4, $5)
"""


async def insert_document_version(
    conn: asyncpg.Connection,
    doc_id: uuid.UUID,
    version_number: int,
    title: str,
    content: str | None,
) -> None:
    """Insère une révision et sa projection texte.

    À appeler dans la transaction du save. Le codec est résolu depuis
    `document.type`, donc la ligne `document` doit déjà exister (c'est le cas
    aux quatre sites d'écriture, y compris à la création).

    Un type de contenu inconnu retombe sur le codec de repli, dont la projection
    est le contenu tel quel : la recherche reste exactement ce qu'elle était.
    """
    codec = await codec_for_document(conn, doc_id)
    await conn.execute(
        _INSERT_SQL,
        doc_id,
        version_number,
        title,
        content,
        codec.to_plain_text(content),
    )
