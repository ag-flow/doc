from __future__ import annotations

import datetime
import uuid

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.documents.changelog import log_change

log = structlog.get_logger(__name__)

# Écritures serveur de valeurs de propriétés, partagées entre la création de
# document (valeurs initiales + contrat required), les comportements
# automatiques (behavior auto_now / auto_now_create) et le changement de type.
# Toutes les fonctions s'exécutent DANS la transaction appelante.


async def upsert_value(
    conn: asyncpg.Connection,
    wk: uuid.UUID,
    doc_id: uuid.UUID,
    prop_id: uuid.UUID,
    prop_type: str,
    value: str,
    prop_slug: str = "",
) -> None:
    """Écrit une valeur (création v1 ou bump de version) sans verrou optimiste client.

    Pour une restricted_list, ``value`` est le slug de la valeur autorisée.
    Les validateurs scalaires et les contraintes de la définition s'appliquent.
    """
    # Import paresseux : service.py importe ce module (héberge les validateurs).
    from docflow.documents import service as doc_svc

    allowed_value_ref: uuid.UUID | None = None
    if prop_type == "restricted_list":
        allowed_value_ref = await conn.fetchval(
            "SELECT id FROM properties_allowed_values WHERE property_def_ref = $1 AND slug = $2",
            prop_id,
            value,
        )
        if allowed_value_ref is None:
            raise HTTPException(
                status_code=422,
                detail=f"valeur autorisée '{value}' introuvable pour cette propriété (I-5)",
            )
        stored_value: str | None = None
    else:
        if prop_type == "int":
            await doc_svc._validate_int(value, prop_slug)
        elif prop_type == "date":
            doc_svc._validate_date(value, prop_slug)
        elif prop_type == "bool":
            doc_svc._validate_bool(value, prop_slug)
        elif prop_type == "url":
            doc_svc._validate_url(value, prop_slug)
        elif prop_type == "float":
            doc_svc._validate_float(value, prop_slug)
        elif prop_type == "reference":
            ref_id = uuid.UUID(value)
            exists = await conn.fetchval(
                "SELECT 1 FROM document "
                "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
                ref_id,
                wk,
            )
            if not exists:
                raise HTTPException(
                    status_code=422,
                    detail=f"document cible '{value}' introuvable dans ce workspace",
                )
            target_ft = await conn.fetchval(
                "SELECT target_functional_type_ref FROM properties_defs WHERE id = $1",
                prop_id,
            )
            if target_ft is not None:
                doc_ft = await conn.fetchval(
                    "SELECT functional_type_ref FROM document WHERE doc_technical_key = $1",
                    ref_id,
                )
                if doc_ft != target_ft:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "le document cible n'est pas du type fonctionnel attendu "
                            "(contrainte target_functional_type_ref)"
                        ),
                    )
        await doc_svc._apply_constraints(conn, prop_id, prop_type, value)
        stored_value = value

    target_doc_ref = uuid.UUID(value) if prop_type == "reference" else None

    pv_row = await conn.fetchrow(
        "SELECT id, version FROM properties_values "
        "WHERE document_ref = $1 AND property_def_ref = $2 FOR UPDATE",
        doc_id,
        prop_id,
    )
    if pv_row is None:
        pv_id: uuid.UUID = await conn.fetchval(
            "INSERT INTO properties_values "
            "(document_ref, property_def_ref, version, workspace_technical_key) "
            "VALUES ($1, $2, 1, $3) RETURNING id",
            doc_id,
            prop_id,
            wk,
        )
        new_v = 1
    else:
        pv_id = pv_row["id"]
        new_v = pv_row["version"] + 1
        await conn.execute("UPDATE properties_values SET version = $1 WHERE id = $2", new_v, pv_id)
    await conn.execute(
        "INSERT INTO properties_value_version "
        "(property_value_ref, version_number, value, allowed_value_ref, target_document_ref) "
        "VALUES ($1, $2, $3, $4, $5)",
        pv_id,
        new_v,
        stored_value,
        allowed_value_ref,
        target_doc_ref,
    )
    await log_change(conn, wk, doc_id, "P")


async def instantiate_default_values(
    conn: asyncpg.Connection,
    wk: uuid.UUID,
    doc_id: uuid.UUID,
    type_id: uuid.UUID | None,
) -> None:
    """Matérialise les valeurs par défaut du type pour les propriétés non renseignées.

    Point d'entrée unique partagé par les deux chemins de création (``create_document``
    côté service/MCP et ``create_document_in_block`` côté UI/bloc) : sans cette parité,
    une propriété required dotée d'un ``default`` restait ``NULL`` après une création
    MCP alors que le chemin bloc l'appliquait (US « défauts du template »).

    Garde d'idempotence : une propriété qui porte déjà une valeur (fournie par
    l'appelant) est ignorée — le défaut ne l'écrase jamais.
    """
    if type_id is None:
        return
    defs = await conn.fetch(
        """
        SELECT pd.id, pd.type, pd.default_value
        FROM properties_defs pd
        LEFT JOIN properties_values pv
            ON pv.property_def_ref = pd.id AND pv.document_ref = $2
        WHERE pd.functional_type_ref = $1
          AND pd.default_value IS NOT NULL
          AND pv.id IS NULL
        """,
        type_id,
        doc_id,
    )
    for pd in defs:
        prop_id: uuid.UUID = pd["id"]
        prop_type: str = pd["type"]
        default_val: str = pd["default_value"]

        allowed_value_ref: uuid.UUID | None = None
        value_to_store: str | None = None
        if prop_type == "restricted_list":
            allowed_value_ref = await conn.fetchval(
                "SELECT id FROM properties_allowed_values "
                "WHERE property_def_ref = $1 AND slug = $2",
                prop_id,
                default_val,
            )
            if allowed_value_ref is None:
                log.warning(
                    "default_value_not_found",
                    prop_id=str(prop_id),
                    default_val=default_val,
                )
                continue
        else:
            value_to_store = default_val

        pv_id: uuid.UUID = await conn.fetchval(
            "INSERT INTO properties_values "
            "(document_ref, property_def_ref, version, workspace_technical_key) "
            "VALUES ($1, $2, 1, $3) RETURNING id",
            doc_id,
            prop_id,
            wk,
        )
        await conn.execute(
            "INSERT INTO properties_value_version "
            "(property_value_ref, version_number, value, allowed_value_ref) "
            "VALUES ($1, 1, $2, $3)",
            pv_id,
            value_to_store,
            allowed_value_ref,
        )


async def assert_required_satisfied(
    conn: asyncpg.Connection,
    doc_id: uuid.UUID,
    type_id: uuid.UUID,
) -> None:
    """Refuse (422) si des propriétés required du type restent non satisfaites.

    Une required est satisfaite par : une valeur stockée, une default_value,
    ou un behavior (le serveur la renseigne lui-même). Le message liste les
    slugs manquants — exploitable tel quel par un agent MCP.
    """
    rows = await conn.fetch(
        """
        SELECT pd.slug
        FROM properties_defs pd
        LEFT JOIN properties_values pv
            ON pv.property_def_ref = pd.id AND pv.document_ref = $2
        WHERE pd.functional_type_ref = $1
          AND pd.required
          AND pd.default_value IS NULL
          AND pd.behavior IS NULL
          AND pv.id IS NULL
        ORDER BY pd.slug
        """,
        type_id,
        doc_id,
    )
    if rows:
        missing = ", ".join(r["slug"] for r in rows)
        raise HTTPException(
            status_code=422,
            detail=(
                f"écriture refusée : propriétés obligatoires non renseignées : {missing} — "
                "les fournir dans 'properties' (slug → valeur ; pour une restricted_list, "
                "le slug de la valeur autorisée)"
            ),
        )


async def apply_behaviors(
    conn: asyncpg.Connection,
    wk: uuid.UUID,
    doc_id: uuid.UUID,
    type_id: uuid.UUID | None,
) -> None:
    """Applique les comportements automatiques après un enregistrement.

    auto_now : date courante à chaque enregistrement du document (création,
    contenu/titre, valeur de propriété). auto_now_create : posée seulement si
    aucune valeur n'existe encore (création ou changement de type).
    """
    if type_id is None:
        return
    today = datetime.date.today().isoformat()
    rows = await conn.fetch(
        """
        SELECT pd.id, pd.type, pd.behavior, pv.id AS pv_id
        FROM properties_defs pd
        LEFT JOIN properties_values pv
            ON pv.property_def_ref = pd.id AND pv.document_ref = $2
        WHERE pd.functional_type_ref = $1 AND pd.behavior IS NOT NULL
        """,
        type_id,
        doc_id,
    )
    for r in rows:
        is_create_only = r["behavior"] == "auto_now_create" and r["pv_id"] is None
        if r["behavior"] == "auto_now" or is_create_only:
            await upsert_value(conn, wk, doc_id, r["id"], r["type"], today)
