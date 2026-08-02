from __future__ import annotations

import time
import uuid
import zlib

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.artifacts.links import build_download_query, verify_download_sig
from docflow.artifacts.parser import extract_artifact_ids

_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-payload"

# ── Parser (unitaire, sans DB) ────────────────────────────────────────────────


def test_extract_single_artifact_id() -> None:
    aid = "550e8400-e29b-41d4-a716-446655440000"
    md = f"![logo](/api/workspaces/mon-ws/artifacts/{aid})"
    assert extract_artifact_ids(md) == {aid}


def test_extract_multiple_and_dedup() -> None:
    a1 = "00000000-0000-0000-0000-000000000001"
    a2 = "00000000-0000-0000-0000-000000000002"
    md = (
        f"![a](/api/workspaces/ws/artifacts/{a1}) "
        f"![b](/api/workspaces/ws/artifacts/{a2}) "
        f"encore [lien](/api/workspaces/ws/artifacts/{a1})"
    )
    assert extract_artifact_ids(md) == {a1, a2}


def test_extract_artifact_scheme_chip() -> None:
    aid = "550e8400-e29b-41d4-a716-446655440000"
    md = f"[Rapport.pdf](artifact://{aid})"
    assert extract_artifact_ids(md) == {aid}


def test_extract_mixed_url_and_scheme_forms() -> None:
    a1 = "00000000-0000-0000-0000-000000000001"
    a2 = "00000000-0000-0000-0000-000000000002"
    md = (
        f"![img](/api/workspaces/ws/artifacts/{a1})\n\n"
        f"[fichier](artifact://{a2})"
    )
    assert extract_artifact_ids(md) == {a1, a2}


def test_extract_ignores_malformed_uuid() -> None:
    md = "![x](/api/workspaces/ws/artifacts/not-a-uuid)"
    assert extract_artifact_ids(md) == set()


def test_extract_ignores_other_urls() -> None:
    md = "![x](https://example.com/image.png) [doc](docflow://doc/550e8400-e29b-41d4-a716-446655440000)"
    assert extract_artifact_ids(md) == set()


def test_extract_empty() -> None:
    assert extract_artifact_ids("") == set()


# ── Liens signés (unitaire, sans DB) ─────────────────────────────────────────


def test_signed_link_roundtrip() -> None:
    aid = uuid.uuid4()
    query = build_download_query("mon-ws", aid, ttl_seconds=60, secret="s3cret")
    # query = "exp=...&sig=..."
    params = dict(p.split("=") for p in query.split("&"))
    assert verify_download_sig("mon-ws", aid, int(params["exp"]), params["sig"], secret="s3cret")


def test_signed_link_rejects_tampered_artifact() -> None:
    aid = uuid.uuid4()
    query = build_download_query("mon-ws", aid, ttl_seconds=60, secret="s3cret")
    params = dict(p.split("=") for p in query.split("&"))
    other = uuid.uuid4()
    assert not verify_download_sig(
        "mon-ws", other, int(params["exp"]), params["sig"], secret="s3cret"
    )


def test_signed_link_rejects_expired() -> None:
    aid = uuid.uuid4()
    exp = int(time.time()) - 10
    # signature valide mais expirée → refus
    from docflow.artifacts.links import _sign

    sig = _sign("mon-ws", aid, exp, "s3cret")
    assert not verify_download_sig("mon-ws", aid, exp, sig, secret="s3cret")


def test_signed_link_rejects_wrong_secret() -> None:
    aid = uuid.uuid4()
    query = build_download_query("mon-ws", aid, ttl_seconds=60, secret="s3cret")
    params = dict(p.split("=") for p in query.split("&"))
    assert not verify_download_sig("mon-ws", aid, int(params["exp"]), params["sig"], secret="autre")


# ── Helpers DB ────────────────────────────────────────────────────────────────


async def _create_doc(
    db_pool: asyncpg.Pool, ws: dict[str, object], block: dict[str, object], title: str
) -> uuid.UUID:
    row = await db_pool.fetchrow(
        "INSERT INTO document "
        "(title, functional_type_ref, workspace_technical_key, data_block_ref) "
        "VALUES ($1, $2, $3, $4) RETURNING doc_technical_key",
        title,
        block["type_id"],
        ws["workspace_technical_key"],
        block["id"],
    )
    assert row is not None
    doc_id: uuid.UUID = row["doc_technical_key"]
    await db_pool.execute(
        "INSERT INTO document_version (document_ref, version_number, title, content) "
        "VALUES ($1, 1, $2, NULL)",
        doc_id,
        title,
    )
    return doc_id


# ── Service : création + dédup ────────────────────────────────────────────────


async def test_create_artifact_stores_and_hashes(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.artifacts import service

    created = await service.create_artifact(
        db_pool, "test-ws", filename="logo.png", data=_PNG, created_by=None, max_bytes=1024
    )
    assert created.deduplicated is False
    assert created.extension == "png"
    assert created.media_type == "image/png"
    assert created.size_bytes == len(_PNG)
    assert created.crc32 == zlib.crc32(_PNG)
    row = await db_pool.fetchrow("SELECT data, sha256 FROM artifact WHERE id = $1", created.id)
    assert row is not None
    assert bytes(row["data"]) == _PNG
    assert row["sha256"] == created.sha256


async def test_create_artifact_dedup_same_content(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.artifacts import service

    first = await service.create_artifact(
        db_pool, "test-ws", filename="a.png", data=_PNG, created_by=None, max_bytes=1024
    )
    second = await service.create_artifact(
        db_pool, "test-ws", filename="b.png", data=_PNG, created_by=None, max_bytes=1024
    )
    assert second.deduplicated is True
    assert second.id == first.id
    count = await db_pool.fetchval(
        "SELECT count(*) FROM artifact WHERE workspace_technical_key = $1",
        test_workspace["workspace_technical_key"],
    )
    assert count == 1


async def test_create_artifact_rejects_oversize(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.artifacts import service

    with pytest.raises(HTTPException) as exc:
        await service.create_artifact(
            db_pool, "test-ws", filename="big.png", data=_PNG, created_by=None, max_bytes=4
        )
    assert exc.value.status_code == 413


async def test_create_artifact_rejects_bad_extension(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.artifacts import service

    with pytest.raises(HTTPException) as exc:
        await service.create_artifact(
            db_pool, "test-ws", filename="script.exe", data=_PNG, created_by=None, max_bytes=1024
        )
    assert exc.value.status_code == 422


async def test_create_artifact_rejects_empty(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.artifacts import service

    with pytest.raises(HTTPException) as exc:
        await service.create_artifact(
            db_pool, "test-ws", filename="vide.png", data=b"", created_by=None, max_bytes=1024
        )
    assert exc.value.status_code == 422


async def test_create_artifact_accepts_non_image_types(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    """La whitelist couvre désormais les binaires du cycle artefacts (pdf,
    audio, archives…), pas seulement les images."""
    from docflow.artifacts import service

    pdf = await service.create_artifact(
        db_pool, "test-ws", filename="rapport.pdf", data=b"%PDF-1.7 fake",
        created_by=None, max_bytes=1024,
    )
    assert pdf.media_type == "application/pdf"
    assert pdf.extension == "pdf"

    audio = await service.create_artifact(
        db_pool, "test-ws", filename="voix.mp3", data=b"ID3 fake-audio",
        created_by=None, max_bytes=1024,
    )
    assert audio.media_type == "audio/mpeg"


async def test_create_artifact_media_type_override_within_whitelist(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    """L'override force un media_type — mais seulement une valeur de la whitelist."""
    from docflow.artifacts import service

    created = await service.create_artifact(
        db_pool, "test-ws", filename="data.txt", data=b"colonnes;valeurs",
        created_by=None, max_bytes=1024, media_type_override="text/csv",
    )
    assert created.media_type == "text/csv"


async def test_create_artifact_media_type_override_rejects_active_type(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    """Un media_type hors whitelist (ex. text/html = XSS servi) est refusé."""
    from docflow.artifacts import service

    with pytest.raises(HTTPException) as exc:
        await service.create_artifact(
            db_pool, "test-ws", filename="page.txt", data=b"<script>alert(1)</script>",
            created_by=None, max_bytes=1024, media_type_override="text/html",
        )
    assert exc.value.status_code == 422


async def test_same_content_different_workspaces_not_deduped(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.artifacts import service

    other = await db_pool.fetchrow(
        "INSERT INTO workspace (slug, label) VALUES ('test-ws-2', 'WS2') "
        "RETURNING workspace_technical_key, slug"
    )
    assert other is not None
    try:
        a = await service.create_artifact(
            db_pool, "test-ws", filename="x.png", data=_PNG, created_by=None, max_bytes=1024
        )
        b = await service.create_artifact(
            db_pool, "test-ws-2", filename="x.png", data=_PNG, created_by=None, max_bytes=1024
        )
        assert a.id != b.id
        assert b.deduplicated is False
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = 'test-ws-2'")


# ── Service : métadonnées + isolation workspace ──────────────────────────────


async def test_get_artifact_meta_and_refcount(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    from docflow.artifacts import service

    created = await service.create_artifact(
        db_pool, "test-ws", filename="m.png", data=_PNG, created_by=None, max_bytes=1024
    )
    meta = await service.get_artifact_meta(db_pool, "test-ws", created.id)
    assert meta.refcount == 0
    doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc réf")
    async with db_pool.acquire() as conn:
        await service.refresh_artifact_references(
            conn,
            doc_id,
            test_workspace["workspace_technical_key"],  # type: ignore[arg-type]
            f"![m](/api/workspaces/test-ws/artifacts/{created.id})",
        )
    meta = await service.get_artifact_meta(db_pool, "test-ws", created.id)
    assert meta.refcount == 1


async def test_refcount_counts_chip_scheme_reference(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Une puce [](artifact://id) compte pour le refcount — sinon l'artefact
    d'un fichier attaché en puce serait purgé comme orphelin."""
    from docflow.artifacts import service

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    created = await service.create_artifact(
        db_pool, "test-ws", filename="joint.pdf", data=_PNG, created_by=None, max_bytes=1024
    )
    doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc puce")
    async with db_pool.acquire() as conn:
        await service.refresh_artifact_references(
            conn, doc_id, wk, f"[Le joint](artifact://{created.id})"
        )
    meta = await service.get_artifact_meta(db_pool, "test-ws", created.id)
    assert meta.refcount == 1


async def test_get_artifact_wrong_workspace_404(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.artifacts import service

    other = await db_pool.fetchrow(
        "INSERT INTO workspace (slug, label) VALUES ('test-ws-iso', 'Iso') "
        "RETURNING workspace_technical_key"
    )
    assert other is not None
    try:
        created = await service.create_artifact(
            db_pool, "test-ws", filename="i.png", data=_PNG, created_by=None, max_bytes=1024
        )
        with pytest.raises(HTTPException) as exc:
            await service.get_artifact_meta(db_pool, "test-ws-iso", created.id)
        assert exc.value.status_code == 404
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = 'test-ws-iso'")


# ── Références : sync + refcount 0 → suppression ─────────────────────────────


async def test_refresh_removes_ref_and_purges_at_zero(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    from docflow.artifacts import service

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    created = await service.create_artifact(
        db_pool, "test-ws", filename="p.png", data=_PNG, created_by=None, max_bytes=1024
    )
    doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc purge")
    url = f"/api/workspaces/test-ws/artifacts/{created.id}"
    async with db_pool.acquire() as conn:
        await service.refresh_artifact_references(conn, doc_id, wk, f"![p]({url})")
        # Le contenu ne référence plus l'artefact → refcount 0 → purge immédiate
        await service.refresh_artifact_references(conn, doc_id, wk, "plus d'image")
    gone = await db_pool.fetchval("SELECT 1 FROM artifact WHERE id = $1", created.id)
    assert gone is None


async def test_refresh_keeps_artifact_referenced_elsewhere(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    from docflow.artifacts import service

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    created = await service.create_artifact(
        db_pool, "test-ws", filename="s.png", data=_PNG, created_by=None, max_bytes=1024
    )
    url = f"/api/workspaces/test-ws/artifacts/{created.id}"
    doc_a = await _create_doc(db_pool, test_workspace, test_block, "Doc A")
    doc_b = await _create_doc(db_pool, test_workspace, test_block, "Doc B")
    async with db_pool.acquire() as conn:
        await service.refresh_artifact_references(conn, doc_a, wk, f"![s]({url})")
        await service.refresh_artifact_references(conn, doc_b, wk, f"![s]({url})")
        # A retire sa référence : l'artefact reste (utilisé par B)
        await service.refresh_artifact_references(conn, doc_a, wk, "rien")
    still = await db_pool.fetchval("SELECT 1 FROM artifact WHERE id = $1", created.id)
    assert still == 1


async def test_refresh_ignores_unknown_and_foreign_artifacts(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Une référence vers un artefact inexistant ou d'un autre workspace ne
    crée pas de ligne (et ne fait pas échouer le save)."""
    from docflow.artifacts import service

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    other = await db_pool.fetchrow(
        "INSERT INTO workspace (slug, label) VALUES ('test-ws-for', 'For') "
        "RETURNING workspace_technical_key"
    )
    assert other is not None
    try:
        foreign = await service.create_artifact(
            db_pool, "test-ws-for", filename="f.png", data=_PNG, created_by=None, max_bytes=1024
        )
        doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc étranger")
        content = (
            f"![gone](/api/workspaces/test-ws/artifacts/{uuid.uuid4()}) "
            f"![foreign](/api/workspaces/test-ws/artifacts/{foreign.id})"
        )
        async with db_pool.acquire() as conn:
            await service.refresh_artifact_references(conn, doc_id, wk, content)
        count = await db_pool.fetchval(
            "SELECT count(*) FROM artifact_reference WHERE document_ref = $1", doc_id
        )
        assert count == 0
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = 'test-ws-for'")


# ── Suppression de document : purge des artefacts orphelins ─────────────────


async def test_delete_document_purges_orphan_artifact(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    from docflow.artifacts import service
    from docflow.documents import service as doc_svc

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    created = await service.create_artifact(
        db_pool, "test-ws", filename="d.png", data=_PNG, created_by=None, max_bytes=1024
    )
    kept = await service.create_artifact(
        db_pool, "test-ws", filename="k.png", data=_PNG + b"2", created_by=None, max_bytes=1024
    )
    url = f"/api/workspaces/test-ws/artifacts/{created.id}"
    kept_url = f"/api/workspaces/test-ws/artifacts/{kept.id}"
    doc_a = await _create_doc(db_pool, test_workspace, test_block, "Doc suppr")
    doc_b = await _create_doc(db_pool, test_workspace, test_block, "Doc garde")
    async with db_pool.acquire() as conn:
        await service.refresh_artifact_references(conn, doc_a, wk, f"![d]({url}) ![k]({kept_url})")
        await service.refresh_artifact_references(conn, doc_b, wk, f"![k]({kept_url})")

    await doc_svc.delete_document(db_pool, "test-ws", doc_a)

    gone = await db_pool.fetchval("SELECT 1 FROM artifact WHERE id = $1", created.id)
    still = await db_pool.fetchval("SELECT 1 FROM artifact WHERE id = $1", kept.id)
    assert gone is None  # plus référencé nulle part → purgé
    assert still == 1  # encore référencé par doc_b → conservé


# ── Purge différée des jamais-référencés ─────────────────────────────────────


async def test_purge_stale_only_old_unreferenced(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    from docflow.artifacts import service

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    stale = await service.create_artifact(
        db_pool, "test-ws", filename="old.png", data=_PNG, created_by=None, max_bytes=1024
    )
    fresh = await service.create_artifact(
        db_pool, "test-ws", filename="new.png", data=_PNG + b"3", created_by=None, max_bytes=1024
    )
    referenced = await service.create_artifact(
        db_pool, "test-ws", filename="ref.png", data=_PNG + b"4", created_by=None, max_bytes=1024
    )
    doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc stale")
    async with db_pool.acquire() as conn:
        await service.refresh_artifact_references(
            conn, doc_id, wk, f"![r](/api/workspaces/test-ws/artifacts/{referenced.id})"
        )
    # Vieillir artificiellement stale + referenced
    await db_pool.execute(
        "UPDATE artifact SET created_at = now() - interval '48 hours' WHERE id = ANY($1::uuid[])",
        [stale.id, referenced.id],
    )
    purged = await service.purge_stale(db_pool, older_than_hours=24)
    assert purged == 1
    assert await db_pool.fetchval("SELECT 1 FROM artifact WHERE id = $1", stale.id) is None
    assert await db_pool.fetchval("SELECT 1 FROM artifact WHERE id = $1", fresh.id) == 1
    assert await db_pool.fetchval("SELECT 1 FROM artifact WHERE id = $1", referenced.id) == 1


# ── Accès public (documents exposés) ─────────────────────────────────────────


async def test_public_fetch_requires_exposed_reference(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Un artefact n'est servi publiquement que si un document exposé le référence."""
    from docflow.artifacts import service

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    created = await service.create_artifact(
        db_pool, "test-ws", filename="pub.png", data=_PNG, created_by=None, max_bytes=1024
    )
    doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc public")
    async with db_pool.acquire() as conn:
        await service.refresh_artifact_references(
            conn, doc_id, wk, f"![p](/api/workspaces/test-ws/artifacts/{created.id})"
        )

    # Document non exposé → 404
    with pytest.raises(HTTPException) as exc:
        await service.fetch_public_artifact_content(db_pool, created.id)
    assert exc.value.status_code == 404

    # Document exposé → servi
    await db_pool.execute("UPDATE document SET exposed = true WHERE doc_technical_key = $1", doc_id)
    data, media_type, filename = await service.fetch_public_artifact_content(db_pool, created.id)
    assert data == _PNG
    assert media_type == "image/png"
    assert filename == "pub.png"

    # Ré-masqué → de nouveau 404
    await db_pool.execute(
        "UPDATE document SET exposed = false WHERE doc_technical_key = $1", doc_id
    )
    with pytest.raises(HTTPException) as exc:
        await service.fetch_public_artifact_content(db_pool, created.id)
    assert exc.value.status_code == 404


async def test_public_fetch_unreferenced_artifact_404(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    """Un artefact sans référence (même existant) n'est jamais servi publiquement."""
    from docflow.artifacts import service

    created = await service.create_artifact(
        db_pool, "test-ws", filename="orph.png", data=_PNG, created_by=None, max_bytes=1024
    )
    with pytest.raises(HTTPException) as exc:
        await service.fetch_public_artifact_content(db_pool, created.id)
    assert exc.value.status_code == 404


async def test_public_fetch_one_exposed_reference_suffices(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Référencé par un doc exposé ET un doc privé → servi (le doc exposé suffit)."""
    from docflow.artifacts import service

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    created = await service.create_artifact(
        db_pool, "test-ws", filename="mix.png", data=_PNG, created_by=None, max_bytes=1024
    )
    url = f"/api/workspaces/test-ws/artifacts/{created.id}"
    doc_pub = await _create_doc(db_pool, test_workspace, test_block, "Doc exposé")
    doc_priv = await _create_doc(db_pool, test_workspace, test_block, "Doc privé")
    async with db_pool.acquire() as conn:
        await service.refresh_artifact_references(conn, doc_pub, wk, f"![m]({url})")
        await service.refresh_artifact_references(conn, doc_priv, wk, f"![m]({url})")
    await db_pool.execute(
        "UPDATE document SET exposed = true WHERE doc_technical_key = $1", doc_pub
    )
    data, _, _ = await service.fetch_public_artifact_content(db_pool, created.id)
    assert data == _PNG


# ── Tools MCP ─────────────────────────────────────────────────────────────────


def _fake_settings() -> object:
    from docflow.config.settings import Settings

    return Settings(
        database_url="postgresql://unused/unused",
        jwt_secret="test-mcp-secret",  # type: ignore[arg-type]
        artifact_link_ttl_seconds=60,
    )


async def _mcp_identity(db_pool: asyncpg.Pool) -> tuple[object, object]:
    """Insère un app_user et ouvre une session MCP JWT à son nom."""
    from docflow.mcp.session import McpSession, set_current_session
    from docflow.schemas.auth import AuthUser

    row = await db_pool.fetchrow(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, true) "
        "ON CONFLICT (email) DO UPDATE SET label = EXCLUDED.label RETURNING id",
        "artifact-mcp@test.local",
        "Artifact MCP",
    )
    assert row is not None
    # Superadmin : bypass de l'accès-utilisateur (workspace de test owner NULL).
    user = AuthUser(
        id=row["id"],
        email="artifact-mcp@test.local",
        label="Artifact MCP",
        is_admin=True,
        validated=True,
        disabled=False,
    )
    token = set_current_session(McpSession(user=user))
    return user, token


async def test_mcp_create_artifact_and_dedup(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    import base64
    import json

    from docflow.mcp import artifact_tools
    from docflow.mcp.session import reset_current_session

    _, token = await _mcp_identity(db_pool)
    try:
        settings = _fake_settings()
        args = {
            "workspace_slug": "test-ws",
            "filename": "mcp.png",
            "data_base64": base64.b64encode(_PNG).decode(),
        }
        first = json.loads(
            (await artifact_tools.handle_create_artifact(db_pool, settings, args))[0].text  # type: ignore[arg-type]
        )
        assert first["deduplicated"] is False
        assert first["url"].endswith(first["id"])
        second = json.loads(
            (await artifact_tools.handle_create_artifact(db_pool, settings, args))[0].text  # type: ignore[arg-type]
        )
        assert second["deduplicated"] is True
        assert second["id"] == first["id"]
    finally:
        reset_current_session(token)  # type: ignore[arg-type]
        await db_pool.execute("DELETE FROM app_user WHERE email = 'artifact-mcp@test.local'")


async def test_mcp_create_artifact_rejects_bad_base64(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    import json

    from docflow.mcp import artifact_tools
    from docflow.mcp.session import reset_current_session

    _, token = await _mcp_identity(db_pool)
    try:
        result = json.loads(
            (
                await artifact_tools.handle_create_artifact(
                    db_pool,
                    _fake_settings(),  # type: ignore[arg-type]
                    {"workspace_slug": "test-ws", "filename": "x.png", "data_base64": "%%%"},
                )
            )[0].text
        )
        assert "error" in result
    finally:
        reset_current_session(token)  # type: ignore[arg-type]
        await db_pool.execute("DELETE FROM app_user WHERE email = 'artifact-mcp@test.local'")


async def test_mcp_create_artifact_from_source_url(
    db_pool: asyncpg.Pool,
    test_workspace: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La voie source_url télécharge côté serveur : les octets ne passent pas inline."""
    import json

    from docflow.mcp import artifact_tools
    from docflow.mcp.session import reset_current_session

    async def _fake_download(url: str, max_bytes: int) -> bytes:
        assert url == "https://example.test/shot.png"
        return _PNG

    monkeypatch.setattr(artifact_tools, "_download_artifact_bytes", _fake_download)

    _, token = await _mcp_identity(db_pool)
    try:
        result = json.loads(
            (
                await artifact_tools.handle_create_artifact(
                    db_pool,
                    _fake_settings(),  # type: ignore[arg-type]
                    {
                        "workspace_slug": "test-ws",
                        "filename": "shot.png",
                        "source_url": "https://example.test/shot.png",
                    },
                )
            )[0].text
        )
        assert result["deduplicated"] is False
        assert result["url"].endswith(result["id"])
        assert result["size_bytes"] == len(_PNG)
    finally:
        reset_current_session(token)  # type: ignore[arg-type]
        await db_pool.execute("DELETE FROM app_user WHERE email = 'artifact-mcp@test.local'")


async def test_mcp_create_artifact_source_url_ssrf_blocked(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    """Une source_url visant une adresse interne est refusée par la garde SSRF."""
    import json

    from docflow.mcp import artifact_tools

    result = json.loads(
        (
            await artifact_tools.handle_create_artifact(
                db_pool,
                _fake_settings(),  # type: ignore[arg-type]
                {
                    "workspace_slug": "test-ws",
                    "filename": "x.png",
                    "source_url": "http://127.0.0.1:9/x.png",
                },
            )
        )[0].text
    )
    assert "error" in result
    assert "source_url" in result["error"]


async def test_mcp_create_artifact_requires_exactly_one_source(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    """Ni data_base64 ni source_url (ou les deux) → refus explicite."""
    import base64
    import json

    from docflow.mcp import artifact_tools

    neither = json.loads(
        (
            await artifact_tools.handle_create_artifact(
                db_pool,
                _fake_settings(),  # type: ignore[arg-type]
                {"workspace_slug": "test-ws", "filename": "x.png"},
            )
        )[0].text
    )
    assert "error" in neither

    both = json.loads(
        (
            await artifact_tools.handle_create_artifact(
                db_pool,
                _fake_settings(),  # type: ignore[arg-type]
                {
                    "workspace_slug": "test-ws",
                    "filename": "x.png",
                    "data_base64": base64.b64encode(_PNG).decode(),
                    "source_url": "https://example.test/x.png",
                },
            )
        )[0].text
    )
    assert "error" in both


async def test_mcp_get_artifact_and_link(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    import json
    import re

    from docflow.artifacts import service
    from docflow.artifacts.links import verify_download_sig
    from docflow.mcp import artifact_tools

    created = await service.create_artifact(
        db_pool, "test-ws", filename="link.png", data=_PNG, created_by=None, max_bytes=1024
    )
    settings = _fake_settings()

    meta = json.loads(
        (
            await artifact_tools.handle_get_artifact(
                db_pool, {"workspace_slug": "test-ws", "artifact_id": str(created.id)}
            )
        )[0].text
    )
    assert meta["filename"] == "link.png"
    assert meta["refcount"] == 0

    link = json.loads(
        (
            await artifact_tools.handle_get_artifact_link(
                db_pool,
                settings,  # type: ignore[arg-type]
                {"workspace_slug": "test-ws", "artifact_id": str(created.id)},
            )
        )[0].text
    )
    m = re.match(r".*/download\?exp=(\d+)&sig=([0-9a-f]{64})$", link["url"])
    assert m is not None
    assert verify_download_sig(
        "test-ws", created.id, int(m.group(1)), m.group(2), secret="test-mcp-secret"
    )


async def test_mcp_list_artifacts_paginated(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    import json

    from docflow.artifacts import service
    from docflow.mcp import artifact_tools

    # Trois artefacts distincts.
    for i in range(3):
        await service.create_artifact(
            db_pool,
            "test-ws",
            filename=f"f{i}.png",
            data=_PNG + bytes([i]),
            created_by=None,
            max_bytes=1024,
        )

    page = json.loads(
        (
            await artifact_tools.handle_list_artifacts(
                db_pool, {"workspace_slug": "test-ws", "limit": 2, "offset": 0}
            )
        )[0].text
    )
    assert page["total"] == 3
    assert page["limit"] == 2
    assert len(page["items"]) == 2
    first = page["items"][0]
    # La liste renvoie toutes les colonnes de la table (sauf le binaire) + refcount.
    expected_keys = {
        "id", "filename", "extension", "media_type", "size_bytes",
        "sha256", "crc32", "created_by", "created_at", "refcount",
    }
    assert expected_keys <= set(first)
    # Jamais le binaire ni la clé technique interne.
    assert "data" not in first
    assert "workspace_technical_key" not in first

    page2 = json.loads(
        (
            await artifact_tools.handle_list_artifacts(
                db_pool, {"workspace_slug": "test-ws", "limit": 2, "offset": 2}
            )
        )[0].text
    )
    assert len(page2["items"]) == 1
    # Aucun recouvrement entre les pages.
    ids1 = {it["id"] for it in page["items"]}
    ids2 = {it["id"] for it in page2["items"]}
    assert ids1.isdisjoint(ids2)


async def test_list_artifacts_filters(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Filtres combinables : filename partiel, sha256 exact, document_id."""
    from docflow.artifacts import service

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    rapport = await service.create_artifact(
        db_pool, "test-ws", filename="Rapport-Q3.pdf", data=b"%PDF q3", created_by=None,
        max_bytes=1024,
    )
    await service.create_artifact(
        db_pool, "test-ws", filename="photo.png", data=_PNG, created_by=None, max_bytes=1024
    )

    # filename partiel, insensible à la casse.
    items, total = await service.list_artifacts(
        db_pool, "test-ws", limit=50, offset=0, filename="rapport"
    )
    assert total == 1 and items[0]["filename"] == "Rapport-Q3.pdf"

    # sha256 exact.
    items, total = await service.list_artifacts(
        db_pool, "test-ws", limit=50, offset=0, sha256=rapport.sha256
    )
    assert total == 1 and items[0]["id"] == rapport.id

    # document_id : artefacts référencés par un document donné.
    doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc réf")
    async with db_pool.acquire() as conn:
        await service.refresh_artifact_references(
            conn, doc_id, wk, f"[r](artifact://{rapport.id})"
        )
    items, total = await service.list_artifacts(
        db_pool, "test-ws", limit=50, offset=0, document_id=doc_id
    )
    assert total == 1 and items[0]["id"] == rapport.id


async def test_mcp_list_artifacts_unknown_workspace(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    import json

    from docflow.mcp import artifact_tools

    result = json.loads(
        (
            await artifact_tools.handle_list_artifacts(
                db_pool, {"workspace_slug": "ws-fantome"}
            )
        )[0].text
    )
    assert "error" in result


async def test_mcp_get_artifact_link_unknown_404(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    import json

    from docflow.mcp import artifact_tools

    result = json.loads(
        (
            await artifact_tools.handle_get_artifact_link(
                db_pool,
                _fake_settings(),  # type: ignore[arg-type]
                {"workspace_slug": "test-ws", "artifact_id": str(uuid.uuid4())},
            )
        )[0].text
    )
    assert "error" in result
