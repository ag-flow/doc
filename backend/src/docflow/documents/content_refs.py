"""Reconstruction des références sortantes d'un document, pilotée par son codec.

Point de bascule de l'épic MLD : l'EXTRACTION des liens dépend du type de
contenu (elle passe par le codec du registre), la RÉCONCILIATION des tables ne
dépend de rien (elle reste dans les modules propriétaires : references,
artifacts, datasets).

Les trois réconciliations étaient systématiquement appelées ensemble : elles ne
forment qu'une seule opération, exposée ici sous un seul appel.
"""

from __future__ import annotations

import uuid

import asyncpg

from docflow.artifacts.service import refresh_artifact_references
from docflow.codecs import codec_for_document
from docflow.datasets.references import refresh_dataset_references
from docflow.references.service import refresh_references


async def refresh_content_references(
    conn: asyncpg.Connection,
    doc_id: uuid.UUID,
    ws_key: uuid.UUID,
    content: str | None,
) -> None:
    """Reconstruit documents + artefacts + datasets référencés par le contenu.

    À appeler dans la transaction du save, après l'écriture de la version.

    Un type de contenu OPAQUE au registre (codec de repli) laisse les références
    existantes INTACTES : la réconciliation supprime les artefacts et datasets
    devenus orphelins, donc traiter « je ne sais pas lire » comme « aucun lien »
    détruirait des données. Cf. ``ContentCodec.extracts_references``.
    """
    codec = await codec_for_document(conn, doc_id)
    if not codec.extracts_references:
        return
    refs = codec.references(content)
    await refresh_references(conn, doc_id, ws_key, refs.documents)
    await refresh_artifact_references(conn, doc_id, ws_key, refs.artifacts)
    await refresh_dataset_references(conn, doc_id, ws_key, refs.datasets)
