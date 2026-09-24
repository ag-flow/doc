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
chaîne), $6 = curseur (last_seq), $7 = block_templates. Un document supprimé (jointure NULL) est
exclu dès qu'un filtre bloc/type est posé ; un event SANS document (cycle de vie
d'un workspace ou d'un bloc) en est au contraire exempté — les filtres
documentaires ne s'appliquent pas à ce qui n'est pas un document.
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
LEFT JOIN functional_type bft ON bft.id = b.functional_type_ref
WHERE de.workspace_technical_key = ANY($1::uuid[])
  AND de.event_code = ANY($2::text[])
  -- Périmètre de blocs : UNION des deux critères. Aucun des deux posé = aucune
  -- restriction ; l'un ou l'autre posé = le bloc doit satisfaire au moins un.
  -- Le template d'un bloc est la provenance de son type RACINE (0038).
  -- Un event de CONTENANT (workspace créé, bloc créé) ne porte pas de document :
  -- les filtres documentaires ne le concernent pas, il passe tel quel. Sans cette
  -- exemption, poser n'importe quel filtre le ferait disparaître en silence.
  -- `de.document_ref IS NULL` et non `d.* IS NULL` : un document SUPPRIMÉ garde
  -- sa référence et reste, lui, exclu dès qu'un filtre est posé.
  AND (
        de.document_ref IS NULL
        OR (cardinality($3::text[]) = 0 AND cardinality($7::text[]) = 0)
        OR b.slug = ANY($3::text[])
        OR bft.source_template = ANY($7::text[])
  )
  AND (
        de.document_ref IS NULL
        OR cardinality($4::text[]) = 0
        OR ft.slug = ANY($4::text[])
  )
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
    templates: list[str] | None = None,
) -> list[asyncpg.Record]:
    """Events matchés au-delà du curseur (batch ordonné)."""
    rows: list[asyncpg.Record] = await conn.fetch(
        "SELECT de.seq, de.document_ref, de.event_code, de.business, "
        "de.correlation_id, de.correlation_kind, de.origin, de.traceparent "
        + _FROM_WHERE
        + " AND de.seq > $6 ORDER BY de.seq ASC LIMIT $8",
        wks,
        codes,
        blocks,
        types,
        automation_id,
        cursor,
        templates or [],
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
    templates: list[str] | None = None,
) -> asyncpg.Record | None:
    """Prochain event matché au-delà du curseur (ou None)."""
    return await conn.fetchrow(
        "SELECT de.seq, de.document_ref, de.event_code, de.business, "
        "de.correlation_id, de.correlation_kind, de.origin, de.traceparent "
        + _FROM_WHERE
        + " AND de.seq > $6 ORDER BY de.seq ASC LIMIT 1",
        wks,
        codes,
        blocks,
        types,
        automation_id,
        cursor,
        templates or [],
    )


async def pending_count(
    conn: asyncpg.Connection,
    wks: list[uuid.UUID],
    codes: list[str],
    blocks: list[str],
    types: list[str],
    automation_id: uuid.UUID,
    cursor: int,
    templates: list[str] | None = None,
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
        templates or [],
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
    templates: list[str] | None = None,
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
        templates or [],
    )
    return val or 0


async def consume(conn: asyncpg.Connection, event_seq: int, automation_id: uuid.UUID) -> None:
    """Marque l'event consommé par l'automate (stop_chain, appel réussi).
    Le premier consommateur gagne (jamais écrasé)."""
    await conn.execute(
        "UPDATE document_event SET consumed_by = $1 WHERE seq = $2 AND consumed_by IS NULL",
        automation_id,
        event_seq,
    )
