from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import httpx
import structlog
from fastapi import HTTPException

from docflow.schemas.contracts import (
    ContractDetailOut,
    ContractImport,
    ContractOut,
    ContractUpdate,
    OperationOut,
)

log = structlog.get_logger(__name__)

_ALLOWED_METHODS = {"get", "post", "put", "patch", "delete"}


# ── Parsing OpenAPI ───────────────────────────────────────────────────────────


def _resolve_ref(raw_spec: Any, ref: str) -> Any:
    """Résout un $ref de type '#/components/schemas/...' (1 niveau)."""
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return {}
    parts = ref.lstrip("#/").split("/")
    node: object = raw_spec
    for p in parts:
        if not isinstance(node, dict):
            return {}
        node = node.get(p, {})
    return node if isinstance(node, dict) else {}


def _body_skeleton(raw_spec: Any, op: Any) -> dict[str, object] | None:
    """Génère un squelette JSON depuis le requestBody de l'opération."""
    rb = op.get("requestBody")
    if not rb:
        return None
    content = rb.get("content", {})
    schema: Any = None
    for media in ("application/json", "*/*"):
        if media in content:
            schema = content[media].get("schema")
            break
    if not schema:
        return None
    if "$ref" in schema:
        schema = _resolve_ref(raw_spec, schema["$ref"])
    if not schema or schema.get("type") != "object":
        return None
    props = schema.get("properties", {})
    result: dict[str, object] = {}
    for name, prop in props.items():
        t = prop.get("type", "string")
        if t == "string":
            result[name] = ""
        elif t in ("integer", "number"):
            result[name] = 0
        elif t == "boolean":
            result[name] = False
        elif t == "array":
            result[name] = []
        else:
            result[name] = None
    return result or None


def list_operations(raw_spec: Any) -> list[OperationOut]:
    ops: list[OperationOut] = []
    for path, item in raw_spec.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method not in _ALLOWED_METHODS or not isinstance(op, dict):
                continue
            ops.append(
                OperationOut(
                    operation_id=op.get("operationId"),
                    method=method.upper(),
                    path=path,
                    summary=op.get("summary"),
                    parameters=op.get("parameters", []),
                    request_body=op.get("requestBody"),
                    body_skeleton=_body_skeleton(raw_spec, op),
                )
            )
    return ops


def _extract_version(raw_spec: Any) -> str | None:
    info = raw_spec.get("info")
    if isinstance(info, dict):
        return info.get("version")
    return None


def _row_to_out(row: asyncpg.Record) -> ContractOut:
    return ContractOut(**dict(row))


# ── CRUD ──────────────────────────────────────────────────────────────────────


async def list_contracts(pool: asyncpg.Pool) -> list[ContractOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, label, source_url, version, imported_at, updated_at "
            "FROM openapi_contract ORDER BY label"
        )
    return [_row_to_out(r) for r in rows]


async def import_contract(pool: asyncpg.Pool, body: ContractImport) -> ContractOut:
    version = _extract_version(body.raw_spec)
    raw_json = json.dumps(body.raw_spec)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO openapi_contract (label, source_url, version, raw_spec) "
            "VALUES ($1, $2, $3, $4::jsonb) "
            "RETURNING id, label, source_url, version, imported_at, updated_at",
            body.label,
            body.source_url,
            version,
            raw_json,
        )
    assert row is not None
    return _row_to_out(row)


async def get_contract_detail(pool: asyncpg.Pool, contract_id: uuid.UUID) -> ContractDetailOut:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, label, source_url, version, imported_at, updated_at, raw_spec "
            "FROM openapi_contract WHERE id = $1",
            contract_id,
        )
    if row is None:
        raise HTTPException(404, "Contrat introuvable.")
    raw_spec: dict[str, object] = json.loads(row["raw_spec"])
    contract = ContractOut(
        id=row["id"],
        label=row["label"],
        source_url=row["source_url"],
        version=row["version"],
        imported_at=row["imported_at"],
        updated_at=row["updated_at"],
    )
    return ContractDetailOut(contract=contract, operations=list_operations(raw_spec))


async def update_contract(
    pool: asyncpg.Pool, contract_id: uuid.UUID, body: ContractUpdate
) -> ContractOut:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE openapi_contract SET label=$1, updated_at=now() WHERE id=$2 "
            "RETURNING id, label, source_url, version, imported_at, updated_at",
            body.label,
            contract_id,
        )
    if row is None:
        raise HTTPException(404, "Contrat introuvable.")
    return _row_to_out(row)


async def refresh_contract(pool: asyncpg.Pool, contract_id: uuid.UUID) -> ContractOut:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT source_url FROM openapi_contract WHERE id = $1", contract_id
        )
    if row is None:
        raise HTTPException(404, "Contrat introuvable.")
    if not row["source_url"]:
        raise HTTPException(422, "Ce contrat n'a pas de source_url (import manuel).")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(row["source_url"])
        resp.raise_for_status()
        raw_spec: dict[str, object] = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Impossible de récupérer le contrat : {exc}") from exc

    version = _extract_version(raw_spec)
    raw_json = json.dumps(raw_spec)
    async with pool.acquire() as conn:
        updated = await conn.fetchrow(
            "UPDATE openapi_contract SET raw_spec=$1::jsonb, version=$2, updated_at=now() "
            "WHERE id=$3 "
            "RETURNING id, label, source_url, version, imported_at, updated_at",
            raw_json,
            version,
            contract_id,
        )
    assert updated is not None
    log.info("contract_refreshed", contract_id=str(contract_id), version=version)
    return _row_to_out(updated)


async def delete_contract(pool: asyncpg.Pool, contract_id: uuid.UUID) -> None:
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM openapi_contract WHERE id = $1", contract_id)
    if result == "DELETE 0":
        raise HTTPException(404, "Contrat introuvable.")
