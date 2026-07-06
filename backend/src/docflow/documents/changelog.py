from __future__ import annotations

import uuid

import asyncpg


async def log_change(
    conn: asyncpg.Connection,
    wk: uuid.UUID,
    doc_ref: uuid.UUID,
    nature: str,
) -> None:
    """Insère une entrée document dans document_change_log IN-TRANSACTION.

    Nature : C=création, U=version contenu, P=version valeur prop, D=suppression.
    Doit être appelé à l'intérieur d'une transaction déjà ouverte.
    """
    await conn.execute(
        "INSERT INTO document_change_log "
        "(workspace_technical_key, document_ref, nature, entity_kind) "
        "VALUES ($1, $2, $3, 'document')",
        wk,
        doc_ref,
        nature,
    )


async def log_structure_change(
    conn: asyncpg.Connection,
    wk: uuid.UUID,
    entity_kind: str,
    nature: str,
    entity_ref: uuid.UUID | None = None,
) -> None:
    """Insère une entrée structure (type / property / block / template).

    Nature : C=création, U=modification, D=suppression. P est réservé aux
    documents (log_change). Doit être appelé dans la transaction de la
    mutation pour que le feed ne publie jamais un changement non commité.
    """
    await conn.execute(
        "INSERT INTO document_change_log "
        "(workspace_technical_key, document_ref, nature, entity_kind, entity_ref) "
        "VALUES ($1, NULL, $2, $3, $4)",
        wk,
        nature,
        entity_kind,
        entity_ref,
    )
