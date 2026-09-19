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
    """Canonicalise le contenu, puis insère la révision et sa projection texte.

    À appeler dans la transaction du save. Le codec est résolu depuis
    `document.type`, donc la ligne `document` doit déjà exister (c'est le cas
    aux quatre sites d'écriture, y compris à la création).

    C'est ici qu'a lieu la **canonicalisation côté serveur** : forme figée et
    identifiants stables alloués, quel que soit l'auteur ou l'outil d'écriture.
    Elle ne détruit jamais — un contenu illisible est enregistré tel quel (cf.
    `ContentCodec.canonicalize`), le refus étant du ressort de l'API.

    Un type de contenu inconnu retombe sur le codec de repli : ni
    canonicalisation ni projection particulière, le comportement reste celui
    d'avant l'introduction des codecs.
    """
    codec = await codec_for_document(conn, doc_id)
    canonical = codec.canonicalize(content) if content is not None else None
    await conn.execute(
        _INSERT_SQL,
        doc_id,
        version_number,
        title,
        canonical,
        codec.to_plain_text(canonical),
    )
