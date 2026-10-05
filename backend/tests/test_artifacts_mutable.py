"""Artefacts mutables (fiche 38794abe) — update, patch par ancre, if_revision.

Couvre les critères d'acceptation : id stable à travers N écritures + historique
consultable ; écriture sans/avec if_revision périmé refusée ; old_str
ambigu/introuvable rejette tout le patch ; deux mutables identiques → ids
distincts ; patch sur binaire refusé ; canal .html réservé aux mutables ; garde
anti-XSS (text/html jamais servi par les endpoints génériques).
"""

from __future__ import annotations

import json
import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.artifacts import mutable, service
from docflow.artifacts.router import binary_response

_MAX = 10 * 1024 * 1024
_PNG = b"\x89PNG\r\n\x1a\n" + b"binary-body"


async def _make_user(pool: asyncpg.Pool, email: str) -> uuid.UUID:
    return await pool.fetchval(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, true) "
        "ON CONFLICT (email) DO UPDATE SET label = EXCLUDED.label RETURNING id",
        email,
        email,
    )


# ── apply_anchor_edits (fonction pure) ────────────────────────────────────────


def test_anchor_edit_exact_once() -> None:
    assert mutable.apply_anchor_edits(
        "alpha beta gamma", [{"old_str": "beta", "new_str": "BETA"}]
    ) == ("alpha BETA gamma")


def test_anchor_edit_missing_rejects_all() -> None:
    with pytest.raises(HTTPException) as exc:
        mutable.apply_anchor_edits("abc", [{"old_str": "zzz", "new_str": "x"}])
    assert exc.value.status_code == 422


def test_anchor_edit_ambiguous_rejects_all() -> None:
    with pytest.raises(HTTPException) as exc:
        mutable.apply_anchor_edits("aa aa", [{"old_str": "aa", "new_str": "b"}])
    assert exc.value.status_code == 422


def test_anchor_edit_multi_atomic_on_original() -> None:
    out = mutable.apply_anchor_edits(
        "one two", [{"old_str": "one", "new_str": "1"}, {"old_str": "two", "new_str": "2"}]
    )
    assert out == "1 2"


def test_anchor_edit_overlap_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        mutable.apply_anchor_edits(
            "abcdef", [{"old_str": "abc", "new_str": "x"}, {"old_str": "cde", "new_str": "y"}]
        )
    assert exc.value.status_code == 422


def test_anchor_edit_empty_old_rejected() -> None:
    with pytest.raises(HTTPException):
        mutable.apply_anchor_edits("abc", [{"old_str": "", "new_str": "x"}])


# ── Canal .html + exclusion de dédup ──────────────────────────────────────────


async def test_html_channel_requires_mutable(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    # Mutable .html → canal dédié, media_type text/html.
    created = await service.create_artifact(
        db_pool,
        "test-ws",
        filename="m.html",
        data=b"<h1>hi</h1>",
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    assert created.media_type == "text/html"
    assert created.extension == "html"
    # Non mutable .html → refusé (extension hors registre, denylist intact).
    with pytest.raises(HTTPException) as exc:
        await service.create_artifact(
            db_pool,
            "test-ws",
            filename="x.html",
            data=b"<h1>hi</h1>",
            created_by=None,
            max_bytes=_MAX,
            mutable=False,
        )
    assert exc.value.status_code == 422


async def test_mutable_excluded_from_dedup(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    body = b"<h1>same</h1>"
    a = await service.create_artifact(
        db_pool,
        "test-ws",
        filename="a.html",
        data=body,
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    b = await service.create_artifact(
        db_pool,
        "test-ws",
        filename="b.html",
        data=body,
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    assert a.id != b.id  # deux mutables de contenu identique = ids distincts
    assert a.deduplicated is False and b.deduplicated is False


async def test_non_mutable_still_deduplicates(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    body = b"dedup-me"
    a = await service.create_artifact(
        db_pool, "test-ws", filename="a.txt", data=body, created_by=None, max_bytes=_MAX
    )
    b = await service.create_artifact(
        db_pool, "test-ws", filename="b.txt", data=body, created_by=None, max_bytes=_MAX
    )
    assert a.id == b.id and b.deduplicated is True  # comportement immuable préservé


# ── update : id stable, révisions, if_revision ────────────────────────────────


async def test_update_increments_revision_stable_id_and_history(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    uid = await _make_user(db_pool, "mut-upd@test.local")
    try:
        created = await service.create_artifact(
            db_pool,
            "test-ws",
            filename="s.html",
            data=b"<h1>v1</h1>",
            created_by=uid,
            max_bytes=_MAX,
            mutable=True,
        )
        r2 = await mutable.update_artifact(
            db_pool,
            "test-ws",
            created.id,
            data=b"<h1>v2</h1>",
            if_revision=1,
            updated_by=uid,
            max_bytes=_MAX,
        )
        assert r2["id"] == created.id and r2["revision"] == 2
        r3 = await mutable.update_artifact(
            db_pool,
            "test-ws",
            created.id,
            data=b"<h1>v3</h1>",
            if_revision=2,
            updated_by=uid,
            max_bytes=_MAX,
        )
        assert r3["revision"] == 3

        meta = await service.get_artifact_meta(db_pool, "test-ws", created.id)
        assert meta.mutable is True and meta.revision == 3

        revs = await mutable.list_revisions(db_pool, "test-ws", created.id)
        assert [r["revision"] for r in revs] == [1, 2, 3]

        # La révision 1 reste lisible telle qu'à l'origine.
        data, media_type, filename = await mutable.fetch_revision_content(
            db_pool, "test-ws", created.id, 1
        )
        assert data == b"<h1>v1</h1>" and media_type == "text/html" and filename == "s.html"
    finally:
        await db_pool.execute("DELETE FROM app_user WHERE email = 'mut-upd@test.local'")


async def test_update_stale_revision_refused_with_current(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    created = await service.create_artifact(
        db_pool,
        "test-ws",
        filename="c.html",
        data=b"<p>a</p>",
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    await mutable.update_artifact(
        db_pool,
        "test-ws",
        created.id,
        data=b"<p>b</p>",
        if_revision=1,
        updated_by=None,
        max_bytes=_MAX,
    )
    with pytest.raises(HTTPException) as exc:
        await mutable.update_artifact(
            db_pool,
            "test-ws",
            created.id,
            data=b"<p>c</p>",
            if_revision=1,
            updated_by=None,
            max_bytes=_MAX,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["current_revision"] == 2  # type: ignore[index]


async def test_update_non_mutable_refused(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    created = await service.create_artifact(
        db_pool, "test-ws", filename="im.txt", data=b"immutable", created_by=None, max_bytes=_MAX
    )
    with pytest.raises(HTTPException) as exc:
        await mutable.update_artifact(
            db_pool,
            "test-ws",
            created.id,
            data=b"x",
            if_revision=1,
            updated_by=None,
            max_bytes=_MAX,
        )
    assert exc.value.status_code == 409


# ── patch : ancre, atomicité, binaire refusé ──────────────────────────────────


async def test_patch_applies_and_bumps_revision(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    created = await service.create_artifact(
        db_pool,
        "test-ws",
        filename="p.txt",
        data=b"alpha beta gamma",
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    res = await mutable.patch_artifact(
        db_pool,
        "test-ws",
        created.id,
        edits=[{"old_str": "beta", "new_str": "BETA"}],
        if_revision=1,
        updated_by=None,
        max_bytes=_MAX,
    )
    assert res["revision"] == 2
    data, _, _ = await mutable.fetch_revision_content(db_pool, "test-ws", created.id, 2)
    assert data == b"alpha BETA gamma"


async def test_patch_ambiguous_writes_nothing(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    created = await service.create_artifact(
        db_pool,
        "test-ws",
        filename="q.txt",
        data=b"aa aa",
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    with pytest.raises(HTTPException) as exc:
        await mutable.patch_artifact(
            db_pool,
            "test-ws",
            created.id,
            edits=[{"old_str": "aa", "new_str": "b"}],
            if_revision=1,
            updated_by=None,
            max_bytes=_MAX,
        )
    assert exc.value.status_code == 422
    meta = await service.get_artifact_meta(db_pool, "test-ws", created.id)
    assert meta.revision == 1  # rien écrit


async def test_patch_binary_refused(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    created = await service.create_artifact(
        db_pool,
        "test-ws",
        filename="b.png",
        data=_PNG,
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    with pytest.raises(HTTPException) as exc:
        await mutable.patch_artifact(
            db_pool,
            "test-ws",
            created.id,
            edits=[{"old_str": "PNG", "new_str": "x"}],
            if_revision=1,
            updated_by=None,
            max_bytes=_MAX,
        )
    assert exc.value.status_code == 422


# ── Garde de service anti-XSS ─────────────────────────────────────────────────


def test_binary_response_refuses_html() -> None:
    with pytest.raises(HTTPException) as exc:
        binary_response(b"<script>alert(1)</script>", "text/html", "m.html", attachment=False)
    assert exc.value.status_code == 404
    # Même en attachment : jamais servi par la voie générique.
    with pytest.raises(HTTPException):
        binary_response(b"<h1>x</h1>", "text/html", "m.html", attachment=True)


# ── Surface MCP ───────────────────────────────────────────────────────────────


async def _session(db_pool: asyncpg.Pool, email: str) -> object:
    from docflow.mcp.session import McpSession, set_current_session
    from docflow.schemas.auth import AuthUser

    uid = await _make_user(db_pool, email)
    user = AuthUser(id=uid, email=email, label=email, is_admin=True, validated=True, disabled=False)
    return set_current_session(McpSession(user=user))


def _settings() -> object:
    from docflow.config.settings import Settings

    return Settings(
        database_url="postgresql://unused/unused",
        jwt_secret="test-mutable-secret",  # type: ignore[arg-type]
        public_base_url="https://doc.example.test",
    )


async def test_mcp_create_update_patch_get_flow(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    import base64

    from docflow.mcp import artifact_tools
    from docflow.mcp.session import reset_current_session

    token = await _session(db_pool, "mut-mcp@test.local")
    try:
        settings = _settings()
        created = json.loads(
            (
                await artifact_tools.handle_create_artifact(
                    db_pool,
                    settings,
                    {  # type: ignore[arg-type]
                        "workspace_slug": "test-ws",
                        "filename": "screen.html",
                        "data_base64": base64.b64encode(b"<h1>hello</h1>").decode(),
                        "mutable": True,
                    },
                )
            )[0].text
        )
        assert created["media_type"] == "text/html"
        art_id = created["id"]

        # update sans if_revision → refus explicite.
        missing = json.loads(
            (
                await artifact_tools.handle_update_artifact(
                    db_pool,
                    settings,
                    {"workspace_slug": "test-ws", "artifact_id": art_id, "content": "x"},  # type: ignore[arg-type]
                )
            )[0].text
        )
        assert "error" in missing

        upd = json.loads(
            (
                await artifact_tools.handle_update_artifact(
                    db_pool,
                    settings,
                    {  # type: ignore[arg-type]
                        "workspace_slug": "test-ws",
                        "artifact_id": art_id,
                        "content": "<h1>hello world</h1>",
                        "if_revision": 1,
                    },
                )
            )[0].text
        )
        assert upd["revision"] == 2

        patched = json.loads(
            (
                await artifact_tools.handle_patch_artifact(
                    db_pool,
                    settings,
                    {  # type: ignore[arg-type]
                        "workspace_slug": "test-ws",
                        "artifact_id": art_id,
                        "edits": [{"old_str": "world", "new_str": "docflow"}],
                        "if_revision": 2,
                    },
                )
            )[0].text
        )
        assert patched["revision"] == 3

        got = json.loads(
            (
                await artifact_tools.handle_get_artifact(
                    db_pool, {"workspace_slug": "test-ws", "artifact_id": art_id}
                )
            )[0].text
        )
        assert got["mutable"] is True and got["revision"] == 3
        assert [r["revision"] for r in got["revisions"]] == [1, 2, 3]

        data_rev1 = json.loads(
            (
                await artifact_tools.handle_get_artifact_data(
                    db_pool,
                    settings,
                    {"workspace_slug": "test-ws", "artifact_id": art_id, "revision": 1},  # type: ignore[arg-type]
                )
            )[0].text
        )
        assert data_rev1["content"] == "<h1>hello</h1>" and data_rev1["encoding"] == "utf-8"
    finally:
        reset_current_session(token)  # type: ignore[arg-type]
        await db_pool.execute("DELETE FROM app_user WHERE email = 'mut-mcp@test.local'")


# ── Rétention des révisions (fiche 97b41148) ──────────────────────────────────


async def _create_and_update(pool: asyncpg.Pool, name: str, n: int, keep: int | None) -> uuid.UUID:
    created = await service.create_artifact(
        pool,
        "test-ws",
        filename=name,
        data=b"<b>1</b>",
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    rev = 1
    for i in range(2, n + 1):
        res = await mutable.update_artifact(
            pool,
            "test-ws",
            created.id,
            data=f"<b>{i}</b>".encode(),
            if_revision=rev,
            updated_by=None,
            max_bytes=_MAX,
            keep=keep,
        )
        rev = int(res["revision"])  # type: ignore[arg-type]
    return created.id


async def test_trim_at_write_keeps_last_n_and_current(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    aid = await _create_and_update(db_pool, "t.html", 5, keep=3)  # révisions 1..5, keep 3
    revs = [r["revision"] for r in await mutable.list_revisions(db_pool, "test-ws", aid)]
    assert revs == [3, 4, 5]  # les 3 dernières ; la courante (5) toujours là
    # La révision courante reste lisible telle quelle.
    data, _, _ = await mutable.fetch_revision_content(db_pool, "test-ws", aid, 5)
    assert data == b"<b>5</b>"


async def test_no_trim_when_keep_none(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    aid = await _create_and_update(db_pool, "u.html", 5, keep=None)  # rétention désactivée
    revs = [r["revision"] for r in await mutable.list_revisions(db_pool, "test-ws", aid)]
    assert revs == [1, 2, 3, 4, 5]


async def test_explicit_prune_keeps_last_n(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    aid = await _create_and_update(db_pool, "p.html", 5, keep=None)
    res = await mutable.prune_artifact_revisions(db_pool, "test-ws", aid, keep=2)
    assert res["revisions_pruned"] == 3 and res["current_revision"] == 5
    revs = [r["revision"] for r in await mutable.list_revisions(db_pool, "test-ws", aid)]
    assert revs == [4, 5]  # courante jamais supprimée


async def test_prune_immutable_no_effect(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    created = await service.create_artifact(
        db_pool, "test-ws", filename="im.txt", data=b"x", created_by=None, max_bytes=_MAX
    )
    res = await mutable.prune_artifact_revisions(db_pool, "test-ws", created.id, keep=1)
    assert res["revisions_pruned"] == 0


async def test_prune_keep_below_one_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    aid = await _create_and_update(db_pool, "z.html", 2, keep=None)
    with pytest.raises(HTTPException) as exc:
        await mutable.prune_artifact_revisions(db_pool, "test-ws", aid, keep=0)
    assert exc.value.status_code == 422


# ── Robustesse booléenne de `mutable` (clients qui stringifient) ──────────────


def test_as_bool_tolerant() -> None:
    from docflow.mcp.artifact_tools import _as_bool

    assert _as_bool(True) is True
    assert _as_bool("true") is True
    assert _as_bool("True") is True
    assert _as_bool("1") is True
    assert _as_bool("yes") is True
    assert _as_bool(False) is False
    assert _as_bool("false") is False
    assert _as_bool("") is False
    assert _as_bool(None) is False
    assert _as_bool(0) is False


async def test_mcp_create_mutable_accepts_string_boolean(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    """Régression : `mutable="true"` (chaîne) doit créer une maquette .html —
    sinon l'artefact naît immuable et .html est refusé (bug « mime refusé »)."""
    import base64

    from docflow.mcp import artifact_tools
    from docflow.mcp.session import reset_current_session

    token = await _session(db_pool, "mut-strbool@test.local")
    try:
        created = json.loads(
            (
                await artifact_tools.handle_create_artifact(
                    db_pool,
                    _settings(),  # type: ignore[arg-type]
                    {
                        "workspace_slug": "test-ws",
                        "filename": "ecran.html",
                        "data_base64": base64.b64encode(b"<html><body>hi</body></html>").decode(),
                        "mutable": "true",  # chaîne, pas booléen
                    },
                )
            )[0].text
        )
        assert "error" not in created
        assert created["media_type"] == "text/html"
    finally:
        reset_current_session(token)  # type: ignore[arg-type]
        await db_pool.execute("DELETE FROM app_user WHERE email = 'mut-strbool@test.local'")
