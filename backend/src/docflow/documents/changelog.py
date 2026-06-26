from __future__ import annotations

import uuid

import asyncpg


async def log_change(
    conn: asyncpg.Connection,
    wk: uuid.UUID,
    doc_ref: uuid.UUID,
    nature: str,
) -> None:
    """Insère une ligne dans document_change_log IN-TRANSACTION.

    Nature : C=création, U=version contenu, P=version valeur prop, D=suppression.
    Doit être appelé à l'intérieur d'une transaction déjà ouverte.
    """
    await conn.execute(
        "INSERT INTO document_change_log (workspace_technical_key, document_ref, nature) "
        "VALUES ($1, $2, $3)",
        wk,
        doc_ref,
        nature,
    )
