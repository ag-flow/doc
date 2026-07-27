"""Références ``dataset://id`` document → dataset + cycle de vie.

Miroir exact du volet références des artefacts (``artifacts/service.py``) :
les lignes ``dataset_reference`` d'un document sont reconstruites à chaque save
dans la transaction d'enregistrement ; un dataset dont la dernière référence
disparaît est supprimé (refcount 0) ; les datasets jamais référencés et vieux
sont purgés périodiquement par le worker.
"""

from __future__ import annotations

import uuid

import asyncpg

from docflow.datasets.parser import extract_dataset_ids


async def refresh_dataset_references(
    conn: asyncpg.Connection,
    doc_id: uuid.UUID,
    ws_key: uuid.UUID,
    content: str | None,
) -> None:
    """Reconstruit les références datasets du document depuis son contenu.

    Doit être appelé dans la même transaction que le save. Ne conserve que les
    datasets du MÊME workspace qui existent ; les références vers un dataset
    inexistant ou d'un autre workspace sont ignorées (le save n'échoue jamais).
    Un dataset dont la dernière référence disparaît est supprimé immédiatement.
    """
    parsed = extract_dataset_ids(content)
    old_rows = await conn.fetch(
        "SELECT dataset_ref FROM dataset_reference WHERE document_ref = $1", doc_id
    )
    old_ids = {r["dataset_ref"] for r in old_rows}
    await conn.execute("DELETE FROM dataset_reference WHERE document_ref = $1", doc_id)

    new_ids: set[uuid.UUID] = set()
    if parsed:
        rows = await conn.fetch(
            "SELECT id FROM dataset WHERE workspace_technical_key = $1 AND id = ANY($2::uuid[])",
            ws_key,
            [uuid.UUID(d) for d in parsed],
        )
        new_ids = {r["id"] for r in rows}
        if new_ids:
            await conn.executemany(
                "INSERT INTO dataset_reference (dataset_ref, document_ref, "
                "workspace_technical_key) VALUES ($1, $2, $3)",
                [(did, doc_id, ws_key) for did in new_ids],
            )

    removed = old_ids - new_ids
    if removed:
        await purge_unreferenced_datasets(conn, list(removed))


async def purge_unreferenced_datasets(
    conn: asyncpg.Connection, dataset_ids: list[uuid.UUID]
) -> int:
    """Supprime, parmi les candidats, les datasets sans aucune référence."""
    if not dataset_ids:
        return 0
    result = await conn.execute(
        """
        DELETE FROM dataset d
        WHERE d.id = ANY($1::uuid[])
          AND NOT EXISTS (SELECT 1 FROM dataset_reference r WHERE r.dataset_ref = d.id)
        """,
        dataset_ids,
    )
    return int(result.split()[-1])


async def purge_stale_datasets(pool: asyncpg.Pool, *, older_than_hours: int) -> int:
    """Purge les datasets jamais référencés plus vieux que le seuil.

    Couvre le cas d'un dataset créé dans un brouillon jamais enregistré :
    aucune référence ne sera jamais posée, la règle refcount-0 ne s'applique
    donc pas. Appelé périodiquement par le worker.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM dataset d
            WHERE NOT EXISTS (SELECT 1 FROM dataset_reference r WHERE r.dataset_ref = d.id)
              AND d.created_at < now() - make_interval(hours => $1)
            """,
            older_than_hours,
        )
    return int(result.split()[-1])
