from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import httpx
import structlog
from fastapi import HTTPException

from docflow.net.ssrf import SSRFError, validate_public_url
from docflow.schemas.contracts import (
    AuthHeaderRequirement,
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


def _auth_headers_for(raw_spec: Any, op: Any) -> list[AuthHeaderRequirement]:
    """Headers d'auth requis par l'opération, déduits des securitySchemes.

    Sécurité effective = celle de l'opération, sinon celle de la racine.
    Gère HTTP bearer/basic (→ Authorization) et apiKey-in-header (→ son name).
    Les autres schémas (oauth2, apiKey in query/cookie…) sont ignorés.
    """
    comps = raw_spec.get("components")
    schemes = comps.get("securitySchemes", {}) if isinstance(comps, dict) else {}
    security = op.get("security")
    if security is None:
        security = raw_spec.get("security", [])
    if not isinstance(security, list) or not isinstance(schemes, dict):
        return []

    seen: set[str] = set()
    result: list[AuthHeaderRequirement] = []
    for req in security:
        if not isinstance(req, dict):
            continue
        for scheme_name in req:
            scheme = schemes.get(scheme_name)
            if not isinstance(scheme, dict):
                continue
            stype = scheme.get("type")
            header: str | None = None
            prefix = ""
            if stype == "http":
                s = str(scheme.get("scheme", "")).lower()
                if s == "bearer":
                    header, prefix = "Authorization", "Bearer "
                elif s == "basic":
                    header, prefix = "Authorization", "Basic "
            elif stype == "apiKey" and scheme.get("in") == "header":
                name = scheme.get("name")
                if isinstance(name, str):
                    header, prefix = name, ""
            if not header or header in seen:
                continue
            seen.add(header)
            result.append(
                AuthHeaderRequirement(
                    header=header,
                    value_prefix=prefix,
                    scheme_name=str(scheme_name),
                    scheme_type=str(stype or ""),
                )
            )
    return result


def _server_urls(raw_spec: Any) -> list[str]:
    """URLs de serveur déclarées par le contrat (spec.servers[].url)."""
    servers = raw_spec.get("servers")
    if not isinstance(servers, list):
        return []
    return [
        s["url"]
        for s in servers
        if isinstance(s, dict) and isinstance(s.get("url"), str) and s["url"].strip()
    ]


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
                    auth_headers=_auth_headers_for(raw_spec, op),
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


async def _fetch_spec(url: str) -> dict[str, Any]:
    """Récupère un contrat OpenAPI depuis une URL (SSRF-safe). JSON attendu."""
    try:
        await validate_public_url(url)
    except SSRFError as exc:
        raise HTTPException(422, f"URL de source refusée : {exc}") from exc
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        spec = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Impossible de récupérer le contrat : {exc}") from exc
    except ValueError as exc:  # JSON invalide (ex. YAML)
        raise HTTPException(422, f"Le contrat n'est pas du JSON valide : {exc}") from exc
    if not isinstance(spec, dict):
        raise HTTPException(422, "Le contrat récupéré n'est pas un objet OpenAPI.")
    return spec


async def import_contract(pool: asyncpg.Pool, body: ContractImport) -> ContractOut:
    raw_spec: dict[str, Any] = body.raw_spec
    # URL fournie sans spec inline → on télécharge tout de suite (sinon le
    # contrat resterait vide jusqu'à un refresh, et aucune opération n'apparaît).
    if body.source_url and not raw_spec:
        raw_spec = await _fetch_spec(body.source_url)
    version = _extract_version(raw_spec)
    raw_json = json.dumps(raw_spec)
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
    return ContractDetailOut(
        contract=contract,
        operations=list_operations(raw_spec),
        servers=_server_urls(raw_spec),
    )


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

    raw_spec = await _fetch_spec(row["source_url"])
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
