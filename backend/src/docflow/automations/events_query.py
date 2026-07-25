"""Requêtes sur le journal document_event filtrées pour un automate.

Filtre commun : eventCodes déclencheurs + (optionnel) blocs + (optionnel) types
de document, combinés en AND. Un filtre vide = « tous ». Centralisé ici pour
que le worker, le compteur « en attente » et la navigation (next/prev) appliquent
EXACTEMENT le même filtre.

Params positionnels communs : $1 = workspace_technical_key, $2 = eventCodes,
$3 = block_slugs, $4 = functional_type_slugs, $5 = curseur (last_seq).
Un document supprimé (jointure NULL) est exclu dès qu'un filtre bloc/type est posé.
"""

from __future__ import annotations

import uuid

import asyncpg

# Jointures + filtre (sans la borne de curseur, ajoutée par chaque requête).
_FROM_WHERE = """
FROM document_event de
LEFT JOIN document d ON d.doc_technical_key = de.document_ref
LEFT JOIN data_block b ON b.id = d.data_block_ref
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
WHERE de.workspace_technical_key = ANY($1::uuid[])
  AND de.event_code = ANY($2::text[])
  AND (cardinality($3::text[]) = 0 OR b.slug = ANY($3::text[]))
  AND (cardinality($4::text[]) = 0 OR ft.slug = ANY($4::text[]))
"""


async def matching_batch(
    conn: asyncpg.Connection,
    wks: list[uuid.UUID],
    codes: list[str],
    blocks: list[str],
    types: list[str],
    cursor: int,
    limit: int,
) -> list[asyncpg.Record]:
    """Events matchés au-delà du curseur (batch ordonné)."""
    rows: list[asyncpg.Record] = await conn.fetch(
        "SELECT de.seq, de.document_ref, de.event_code, de.business "
        + _FROM_WHERE
        + " AND de.seq > $5 ORDER BY de.seq ASC LIMIT $6",
        wks,
        codes,
        blocks,
        types,
        cursor,
        limit,
    )
    return rows


async def next_matching(
    conn: asyncpg.Connection,
    wks: list[uuid.UUID],
    codes: list[str],
    blocks: list[str],
    types: list[str],
    cursor: int,
) -> asyncpg.Record | None:
    """Prochain event matché au-delà du curseur (ou None)."""
    return await conn.fetchrow(
        "SELECT de.seq, de.document_ref, de.event_code, de.business "
        + _FROM_WHERE
        + " AND de.seq > $5 ORDER BY de.seq ASC LIMIT 1",
        wks,
        codes,
        blocks,
        types,
        cursor,
    )


async def pending_count(
    conn: asyncpg.Connection,
    wks: list[uuid.UUID],
    codes: list[str],
    blocks: list[str],
    types: list[str],
    cursor: int,
) -> int:
    """Nombre d'events matchés au-delà du curseur."""
    n: int = await conn.fetchval(
        "SELECT count(*) " + _FROM_WHERE + " AND de.seq > $5",
        wks,
        codes,
        blocks,
        types,
        cursor,
    )
    return n or 0


async def prev_cursor(
    conn: asyncpg.Connection,
    wks: list[uuid.UUID],
    codes: list[str],
    blocks: list[str],
    types: list[str],
    cursor: int,
) -> int:
    """Nouveau curseur pour « revenir au précédent » : l'event matché juste avant
    le dernier traité redevient courant. 0 si on est déjà au début."""
    val: int = await conn.fetchval(
        "WITH ev AS (SELECT de.seq "
        + _FROM_WHERE
        + "), p AS (SELECT max(seq) AS s FROM ev WHERE seq <= $5) "
        "SELECT COALESCE((SELECT max(seq) FROM ev WHERE seq < (SELECT s FROM p)), 0)",
        wks,
        codes,
        blocks,
        types,
        cursor,
    )
    return val or 0
