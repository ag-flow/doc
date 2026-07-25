"""Requêtes sur le journal document_event filtrées pour un automate.

Filtre commun : eventCodes déclencheurs + (optionnel) blocs + (optionnel) types
de document, combinés en AND, sur TOUS les workspaces couverts. Un filtre vide
= « tous ». Centralisé ici pour que le worker, le compteur « en attente » et la
navigation (next/prev) appliquent EXACTEMENT le même filtre.

Chaîne de responsabilité : un event « consommé » (document_event.consumed_by)
par un automate stop_chain est masqué pour les automates de priorité INFÉRIEURE
(position supérieure dans le workspace de l'event, comparée à l'évaluation).
Le consommateur lui-même et les priorités supérieures le voient toujours.

Params positionnels communs : $1 = workspaces (uuid[]), $2 = eventCodes,
$3 = block_slugs, $4 = functional_type_slugs, $5 = automation_id (pour la
chaîne), $6 = curseur (last_seq). Un document supprimé (jointure NULL) est
exclu dès qu'un filtre bloc/type est posé.
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
  AND (
        de.consumed_by IS NULL
        OR de.consumed_by = $5
        OR NOT EXISTS (
            SELECT 1 FROM automation_workspace bw, automation_workspace mw
            WHERE bw.automation_ref = de.consumed_by
              AND bw.workspace_technical_key = de.workspace_technical_key
              AND mw.automation_ref = $5
              AND mw.workspace_technical_key = de.workspace_technical_key
              AND mw.position > bw.position
        )
  )
"""


async def matching_batch(
    conn: asyncpg.Connection,
    wks: list[uuid.UUID],
    codes: list[str],
    blocks: list[str],
    types: list[str],
    automation_id: uuid.UUID,
    cursor: int,
    limit: int,
) -> list[asyncpg.Record]:
    """Events matchés au-delà du curseur (batch ordonné)."""
    rows: list[asyncpg.Record] = await conn.fetch(
        "SELECT de.seq, de.document_ref, de.event_code, de.business "
        + _FROM_WHERE
        + " AND de.seq > $6 ORDER BY de.seq ASC LIMIT $7",
        wks,
        codes,
        blocks,
        types,
        automation_id,
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
    automation_id: uuid.UUID,
    cursor: int,
) -> asyncpg.Record | None:
    """Prochain event matché au-delà du curseur (ou None)."""
    return await conn.fetchrow(
        "SELECT de.seq, de.document_ref, de.event_code, de.business "
        + _FROM_WHERE
        + " AND de.seq > $6 ORDER BY de.seq ASC LIMIT 1",
        wks,
        codes,
        blocks,
        types,
        automation_id,
        cursor,
    )


async def pending_count(
    conn: asyncpg.Connection,
    wks: list[uuid.UUID],
    codes: list[str],
    blocks: list[str],
    types: list[str],
    automation_id: uuid.UUID,
    cursor: int,
) -> int:
    """Nombre d'events matchés au-delà du curseur."""
    n: int = await conn.fetchval(
        "SELECT count(*) " + _FROM_WHERE + " AND de.seq > $6",
        wks,
        codes,
        blocks,
        types,
        automation_id,
        cursor,
    )
    return n or 0


async def prev_cursor(
    conn: asyncpg.Connection,
    wks: list[uuid.UUID],
    codes: list[str],
    blocks: list[str],
    types: list[str],
    automation_id: uuid.UUID,
    cursor: int,
) -> int:
    """Nouveau curseur pour « revenir au précédent » : l'event matché juste avant
    le dernier traité redevient courant. 0 si on est déjà au début."""
    val: int = await conn.fetchval(
        "WITH ev AS (SELECT de.seq "
        + _FROM_WHERE
        + "), p AS (SELECT max(seq) AS s FROM ev WHERE seq <= $6) "
        "SELECT COALESCE((SELECT max(seq) FROM ev WHERE seq < (SELECT s FROM p)), 0)",
        wks,
        codes,
        blocks,
        types,
        automation_id,
        cursor,
    )
    return val or 0


async def consume(
    conn: asyncpg.Connection, event_seq: int, automation_id: uuid.UUID
) -> None:
    """Marque l'event consommé par l'automate (stop_chain, appel réussi).
    Le premier consommateur gagne (jamais écrasé)."""
    await conn.execute(
        "UPDATE document_event SET consumed_by = $1 WHERE seq = $2 AND consumed_by IS NULL",
        automation_id,
        event_seq,
    )
