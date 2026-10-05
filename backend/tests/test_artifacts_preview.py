"""Serveur de preview des maquettes HTML (fiche 6dd1e16d).

Couvre : signature révision-conscient ; injection du script de mesure ; garde
d'origine (fail closed sans preview_base_url, refus hors hôte dédié) ; CSP
fermée + text/html + Content-Disposition inline ; refus de tout artefact non
HTML ; mint du lien via MCP get_preview_link (réservé aux maquettes mutables).
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from urllib.parse import parse_qs

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.artifacts import preview_router, service
from docflow.artifacts.links import build_preview_query, verify_preview_sig

_HTML = b"<html><body><h1>Maquette</h1></body></html>"
_MAX = 10 * 1024 * 1024


def _settings(preview: str | None = "https://preview.test", render: str | None = None) -> object:
    from docflow.config.settings import Settings

    return Settings(
        database_url="postgresql://unused/unused",
        jwt_secret="test-preview-secret",  # type: ignore[arg-type]
        public_base_url="https://doc.test",
        preview_base_url=preview,
        render_service_url=render,
        render_service_token="tok" if render else None,  # type: ignore[arg-type]
    )


# ── Stub de Request (évite un TestClient sync dans un test async) ─────────────


class _Url:
    def __init__(self, host: str) -> None:
        self.hostname = host


class _State:
    def __init__(self, settings: object, pool: asyncpg.Pool) -> None:
        self.settings = settings
        self.pool = pool


class _App:
    def __init__(self, settings: object, pool: asyncpg.Pool) -> None:
        self.state = _State(settings, pool)


class _Req:
    def __init__(self, settings: object, pool: asyncpg.Pool, host: str) -> None:
        self.app = _App(settings, pool)
        self.url = _Url(host)


def _query_parts(query: str) -> tuple[int, int, str]:
    q = parse_qs(query)
    return int(q["rev"][0]), int(q["exp"][0]), q["sig"][0]


# ── Signature ─────────────────────────────────────────────────────────────────


def test_preview_sig_roundtrip() -> None:
    aid = uuid.uuid4()
    rev, exp, sig = _query_parts(build_preview_query("ws", aid, 2, ttl_seconds=900, secret="s"))
    assert rev == 2
    assert verify_preview_sig("ws", aid, 2, exp, sig, secret="s") is True
    # Lien lié à UNE révision : le même sig ne vaut pas pour une autre révision.
    assert verify_preview_sig("ws", aid, 3, exp, sig, secret="s") is False
    # Ni pour un autre workspace / secret.
    assert verify_preview_sig("other", aid, 2, exp, sig, secret="s") is False
    assert verify_preview_sig("ws", aid, 2, exp, sig, secret="autre") is False


def test_preview_sig_expired() -> None:
    aid = uuid.uuid4()
    rev, exp, sig = _query_parts(build_preview_query("ws", aid, 1, ttl_seconds=-10, secret="s"))
    assert exp < int(time.time())
    assert verify_preview_sig("ws", aid, 1, exp, sig, secret="s") is False


# ── Injection du script de mesure ─────────────────────────────────────────────


def test_inject_measure_before_body_close() -> None:
    out = preview_router._inject_measure("<body>x</body>")
    assert "docflow-preview-height" in out
    assert out.index("docflow-preview-height") < out.index("</body>")


def test_inject_measure_appends_when_no_body() -> None:
    out = preview_router._inject_measure("<h1>x</h1>")
    assert out.startswith("<h1>x</h1>") and "docflow-preview-height" in out


# ── Route de service ──────────────────────────────────────────────────────────


async def _make_maquette(pool: asyncpg.Pool) -> uuid.UUID:
    created = await service.create_artifact(
        pool,
        "test-ws",
        filename="m.html",
        data=_HTML,
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    return created.id


async def test_serve_preview_happy(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    aid = await _make_maquette(db_pool)
    settings = _settings()
    rev, exp, sig = _query_parts(
        build_preview_query("test-ws", aid, 1, ttl_seconds=900, secret="test-preview-secret")
    )
    resp = await preview_router.serve_preview(
        "test-ws",
        aid,
        _Req(settings, db_pool, "preview.test"),
        rev=rev,
        exp=exp,
        sig=sig,  # type: ignore[arg-type]
    )
    assert resp.status_code == 200
    assert resp.media_type == "text/html"
    csp = resp.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "connect-src" not in csp
    assert resp.headers["x-content-type-options"] == "nosniff"
    body = resp.body.decode()
    assert "<h1>Maquette</h1>" in body and "docflow-preview-height" in body


async def test_serve_preview_wrong_host_refused(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    aid = await _make_maquette(db_pool)
    settings = _settings()
    rev, exp, sig = _query_parts(
        build_preview_query("test-ws", aid, 1, ttl_seconds=900, secret="test-preview-secret")
    )
    # Requête arrivant sur l'origine docflow, pas l'origine de preview → 404.
    with pytest.raises(HTTPException) as exc:
        await preview_router.serve_preview(
            "test-ws",
            aid,
            _Req(settings, db_pool, "doc.test"),
            rev=rev,
            exp=exp,
            sig=sig,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 404


async def test_serve_preview_not_configured_refused(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    aid = await _make_maquette(db_pool)
    settings = _settings(preview=None)  # fail closed
    rev, exp, sig = _query_parts(
        build_preview_query("test-ws", aid, 1, ttl_seconds=900, secret="test-preview-secret")
    )
    with pytest.raises(HTTPException) as exc:
        await preview_router.serve_preview(
            "test-ws",
            aid,
            _Req(settings, db_pool, "preview.test"),
            rev=rev,
            exp=exp,
            sig=sig,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 404


async def test_serve_preview_bad_signature_refused(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    aid = await _make_maquette(db_pool)
    settings = _settings()
    with pytest.raises(HTTPException) as exc:
        await preview_router.serve_preview(
            "test-ws",
            aid,
            _Req(settings, db_pool, "preview.test"),
            rev=1,
            exp=int(time.time()) + 900,
            sig="0" * 64,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 404


async def test_serve_preview_non_html_refused(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    # Un artefact mutable NON html (txt) ne se sert pas par la voie preview.
    created = await service.create_artifact(
        db_pool,
        "test-ws",
        filename="n.txt",
        data=b"plain",
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    settings = _settings()
    rev, exp, sig = _query_parts(
        build_preview_query("test-ws", created.id, 1, ttl_seconds=900, secret="test-preview-secret")
    )
    with pytest.raises(HTTPException) as exc:
        await preview_router.serve_preview(
            "test-ws",
            created.id,
            _Req(settings, db_pool, "preview.test"),
            rev=rev,
            exp=exp,
            sig=sig,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 404


# ── MCP get_preview_link ──────────────────────────────────────────────────────


async def test_mcp_get_preview_link(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.mcp import artifact_tools

    aid = await _make_maquette(db_pool)
    settings = _settings()
    res = json.loads(
        (
            await artifact_tools.handle_get_preview_link(
                db_pool,
                settings,
                {"workspace_slug": "test-ws", "artifact_id": str(aid)},  # type: ignore[arg-type]
            )
        )[0].text
    )
    assert res["url"].startswith("https://preview.test/preview/test-ws/")
    assert res["revision"] == 1
    rev, exp, sig = _query_parts(res["url"].split("?", 1)[1])
    assert verify_preview_sig("test-ws", aid, rev, exp, sig, secret="test-preview-secret")


async def test_mcp_get_preview_link_refuses_non_maquette(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.mcp import artifact_tools

    # Artefact non mutable (image) → refusé.
    created = await service.create_artifact(
        db_pool,
        "test-ws",
        filename="i.png",
        data=b"\x89PNG\r\n\x1a\nx",
        created_by=None,
        max_bytes=_MAX,
    )
    settings = _settings()
    res = json.loads(
        (
            await artifact_tools.handle_get_preview_link(
                db_pool,
                settings,
                {"workspace_slug": "test-ws", "artifact_id": str(created.id)},  # type: ignore[arg-type]
            )
        )[0].text
    )
    assert "error" in res


async def test_mcp_get_preview_link_not_configured(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.mcp import artifact_tools

    aid = await _make_maquette(db_pool)
    res = json.loads(
        (
            await artifact_tools.handle_get_preview_link(
                db_pool,
                _settings(preview=None),
                {"workspace_slug": "test-ws", "artifact_id": str(aid)},  # type: ignore[arg-type]
            )
        )[0].text
    )
    assert "error" in res


# ── MCP get_maquette_png (port de rendu) ──────────────────────────────────────


async def test_mcp_get_maquette_png(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from docflow.artifacts import render
    from docflow.mcp import artifact_tools

    seen: dict[str, object] = {}

    async def _fake(settings: object, html: str, *, width: int, height: int = 900) -> bytes:
        seen["width"] = width
        seen["html"] = html
        return b"\x89PNG\r\n\x1a\nDATA"

    monkeypatch.setattr(render, "render_png", _fake)

    aid = await _make_maquette(db_pool)
    out = await artifact_tools.handle_get_maquette_png(
        db_pool,
        _settings(render="http://render.test"),
        {"workspace_slug": "test-ws", "artifact_id": str(aid), "viewport": "mobile"},  # type: ignore[arg-type]
    )
    # 1er contenu = image PNG affichable ; 2e = métadonnées JSON.
    assert out[0].type == "image"
    assert out[0].mimeType == "image/png"
    assert out[0].data == base64.b64encode(b"\x89PNG\r\n\x1a\nDATA").decode("ascii")
    meta = json.loads(out[1].text)
    assert meta["media_type"] == "image/png"
    assert meta["viewport_width"] == 390  # preset mobile
    assert seen["width"] == 390


async def test_mcp_get_maquette_png_not_configured(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.mcp import artifact_tools

    aid = await _make_maquette(db_pool)
    out = await artifact_tools.handle_get_maquette_png(
        db_pool,
        _settings(render=None),
        {"workspace_slug": "test-ws", "artifact_id": str(aid)},  # type: ignore[arg-type]
    )
    assert "error" in json.loads(out[0].text)


async def test_mcp_get_maquette_png_refuses_non_maquette(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.mcp import artifact_tools

    created = await service.create_artifact(
        db_pool,
        "test-ws",
        filename="i.png",
        data=b"\x89PNG\r\n\x1a\nx",
        created_by=None,
        max_bytes=_MAX,
    )
    out = await artifact_tools.handle_get_maquette_png(
        db_pool,
        _settings(render="http://render.test"),
        {"workspace_slug": "test-ws", "artifact_id": str(created.id)},  # type: ignore[arg-type]
    )
    assert "error" in json.loads(out[0].text)
