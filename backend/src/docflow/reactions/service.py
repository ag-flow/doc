"""Service réactions + commentaires sur les documents."""
from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException
from pydantic import BaseModel, field_validator

from docflow.db.helpers import require_workspace

# ── Schémas ──────────────────────────────────────────────────────────────────


class ReactionOut(BaseModel):
    likes: int
    dislikes: int
    my_reaction: int | None  # 1 ou -1 ou None
    last_likes: list[str]    # labels des 5 derniers
    last_dislikes: list[str]


class CommentOut(BaseModel):
    id: uuid.UUID
    author_label: str
    body: str
    is_mine: bool
    reactions: ReactionOut
    created_at: str
    updated_at: str


class ReactionSet(BaseModel):
    model_config = {"extra": "forbid"}
    nature: int

    @field_validator("nature")
    @classmethod
    def _check(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("nature doit être 1 (like) ou -1 (dislike)")
        return v


class CommentCreate(BaseModel):
    model_config = {"extra": "forbid"}
    body: str

    @field_validator("body")
    @classmethod
    def _check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("le commentaire ne peut pas être vide")
        if len(v) > 2000:
            raise ValueError("commentaire trop long (max 2000 caractères)")
        return v


# ── Helpers réactions ────────────────────────────────────────────────────────


async def _doc_reaction_summary(
    conn: asyncpg.Connection, doc_id: uuid.UUID, user_id: uuid.UUID
) -> ReactionOut:
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE nature = 1)::int  AS likes,
            COUNT(*) FILTER (WHERE nature = -1)::int AS dislikes,
            MAX(CASE WHEN user_ref = $2 THEN nature::int END) AS my_reaction
        FROM document_reaction WHERE document_ref = $1
        """,
        doc_id,
        user_id,
    )
    assert row is not None
    like_rows = await conn.fetch(
        """
        SELECT u.label FROM document_reaction dr
        JOIN admin_user u ON u.id = dr.user_ref
        WHERE dr.document_ref = $1 AND dr.nature = 1
        ORDER BY dr.created_at DESC LIMIT 5
        """,
        doc_id,
    )
    dislike_rows = await conn.fetch(
        """
        SELECT u.label FROM document_reaction dr
        JOIN admin_user u ON u.id = dr.user_ref
        WHERE dr.document_ref = $1 AND dr.nature = -1
        ORDER BY dr.created_at DESC LIMIT 5
        """,
        doc_id,
    )
    return ReactionOut(
        likes=row["likes"],
        dislikes=row["dislikes"],
        my_reaction=row["my_reaction"],
        last_likes=[r["label"] for r in like_rows],
        last_dislikes=[r["label"] for r in dislike_rows],
    )


async def _comment_reaction_summary(
    conn: asyncpg.Connection, comment_id: uuid.UUID, user_id: uuid.UUID
) -> ReactionOut:
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE nature = 1)::int  AS likes,
            COUNT(*) FILTER (WHERE nature = -1)::int AS dislikes,
            MAX(CASE WHEN user_ref = $2 THEN nature::int END) AS my_reaction
        FROM comment_reaction WHERE comment_ref = $1
        """,
        comment_id,
        user_id,
    )
    assert row is not None
    like_rows = await conn.fetch(
        """
        SELECT u.label FROM comment_reaction cr
        JOIN admin_user u ON u.id = cr.user_ref
        WHERE cr.comment_ref = $1 AND cr.nature = 1
        ORDER BY cr.created_at DESC LIMIT 5
        """,
        comment_id,
    )
    dislike_rows = await conn.fetch(
        """
        SELECT u.label FROM comment_reaction cr
        JOIN admin_user u ON u.id = cr.user_ref
        WHERE cr.comment_ref = $1 AND cr.nature = -1
        ORDER BY cr.created_at DESC LIMIT 5
        """,
        comment_id,
    )
    return ReactionOut(
        likes=row["likes"],
        dislikes=row["dislikes"],
        my_reaction=row["my_reaction"],
        last_likes=[r["label"] for r in like_rows],
        last_dislikes=[r["label"] for r in dislike_rows],
    )


async def _require_doc(
    conn: asyncpg.Connection, ws_slug: str, doc_id: uuid.UUID
) -> uuid.UUID:
    wk = await require_workspace(conn, ws_slug)
    exists = await conn.fetchval(
        "SELECT 1 FROM document WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
        doc_id,
        wk,
    )
    if not exists:
        raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
    return wk


# ── Réactions sur documents ──────────────────────────────────────────────────


async def get_doc_reactions(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, user_id: uuid.UUID
) -> ReactionOut:
    async with pool.acquire() as conn:
        await _require_doc(conn, ws_slug, doc_id)
        return await _doc_reaction_summary(conn, doc_id, user_id)


async def toggle_doc_reaction(
    pool: asyncpg.Pool,
    ws_slug: str,
    doc_id: uuid.UUID,
    user_id: uuid.UUID,
    nature: int,
) -> ReactionOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _require_doc(conn, ws_slug, doc_id)
            existing: int | None = await conn.fetchval(
                "SELECT nature FROM document_reaction "
                "WHERE document_ref = $1 AND user_ref = $2",
                doc_id,
                user_id,
            )
            if existing == nature:
                await conn.execute(
                    "DELETE FROM document_reaction "
                    "WHERE document_ref = $1 AND user_ref = $2",
                    doc_id,
                    user_id,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO document_reaction (document_ref, user_ref, nature)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (document_ref, user_ref) DO UPDATE SET nature = $3
                    """,
                    doc_id,
                    user_id,
                    nature,
                )
            return await _doc_reaction_summary(conn, doc_id, user_id)


async def remove_doc_reaction(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, user_id: uuid.UUID
) -> ReactionOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _require_doc(conn, ws_slug, doc_id)
            await conn.execute(
                "DELETE FROM document_reaction WHERE document_ref = $1 AND user_ref = $2",
                doc_id,
                user_id,
            )
            return await _doc_reaction_summary(conn, doc_id, user_id)


# ── Commentaires ─────────────────────────────────────────────────────────────


async def list_comments(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, user_id: uuid.UUID
) -> list[CommentOut]:
    async with pool.acquire() as conn:
        await _require_doc(conn, ws_slug, doc_id)
        rows = await conn.fetch(
            """
            SELECT dc.id, dc.body, dc.created_at, dc.updated_at,
                   u.label AS author_label,
                   dc.user_ref
            FROM document_comment dc
            JOIN admin_user u ON u.id = dc.user_ref
            WHERE dc.document_ref = $1
            ORDER BY dc.created_at
            """,
            doc_id,
        )
        result: list[CommentOut] = []
        for r in rows:
            reactions = await _comment_reaction_summary(conn, r["id"], user_id)
            result.append(
                CommentOut(
                    id=r["id"],
                    author_label=r["author_label"],
                    body=r["body"],
                    is_mine=r["user_ref"] == user_id,
                    reactions=reactions,
                    created_at=r["created_at"].isoformat(),
                    updated_at=r["updated_at"].isoformat(),
                )
            )
        return result


async def add_comment(
    pool: asyncpg.Pool,
    ws_slug: str,
    doc_id: uuid.UUID,
    user_id: uuid.UUID,
    user_label: str,
    body: str,
) -> CommentOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _require_doc(conn, ws_slug, doc_id)
            row = await conn.fetchrow(
                """
                INSERT INTO document_comment (document_ref, user_ref, body)
                VALUES ($1, $2, $3)
                RETURNING id, body, created_at, updated_at
                """,
                doc_id,
                user_id,
                body,
            )
            assert row is not None
            return CommentOut(
                id=row["id"],
                author_label=user_label,
                body=row["body"],
                is_mine=True,
                reactions=ReactionOut(
                    likes=0, dislikes=0, my_reaction=None,
                    last_likes=[], last_dislikes=[],
                ),
                created_at=row["created_at"].isoformat(),
                updated_at=row["updated_at"].isoformat(),
            )


async def delete_comment(
    pool: asyncpg.Pool,
    ws_slug: str,
    doc_id: uuid.UUID,
    comment_id: uuid.UUID,
    user_id: uuid.UUID,
    is_superadmin: bool,
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _require_doc(conn, ws_slug, doc_id)
            row = await conn.fetchrow(
                "SELECT user_ref FROM document_comment "
                "WHERE id = $1 AND document_ref = $2",
                comment_id,
                doc_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="commentaire introuvable")
            if row["user_ref"] != user_id and not is_superadmin:
                raise HTTPException(
                    status_code=403, detail="seul l'auteur ou un superadmin peut supprimer"
                )
            await conn.execute("DELETE FROM document_comment WHERE id = $1", comment_id)


# ── Réactions sur commentaires ────────────────────────────────────────────────


async def _require_comment(
    conn: asyncpg.Connection, doc_id: uuid.UUID, comment_id: uuid.UUID
) -> None:
    exists = await conn.fetchval(
        "SELECT 1 FROM document_comment WHERE id = $1 AND document_ref = $2",
        comment_id,
        doc_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="commentaire introuvable")


async def toggle_comment_reaction(
    pool: asyncpg.Pool,
    ws_slug: str,
    doc_id: uuid.UUID,
    comment_id: uuid.UUID,
    user_id: uuid.UUID,
    nature: int,
) -> ReactionOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _require_doc(conn, ws_slug, doc_id)
            await _require_comment(conn, doc_id, comment_id)
            existing: int | None = await conn.fetchval(
                "SELECT nature FROM comment_reaction "
                "WHERE comment_ref = $1 AND user_ref = $2",
                comment_id,
                user_id,
            )
            if existing == nature:
                await conn.execute(
                    "DELETE FROM comment_reaction WHERE comment_ref = $1 AND user_ref = $2",
                    comment_id,
                    user_id,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO comment_reaction (comment_ref, user_ref, nature)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (comment_ref, user_ref) DO UPDATE SET nature = $3
                    """,
                    comment_id,
                    user_id,
                    nature,
                )
            return await _comment_reaction_summary(conn, comment_id, user_id)


async def remove_comment_reaction(
    pool: asyncpg.Pool,
    ws_slug: str,
    doc_id: uuid.UUID,
    comment_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ReactionOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _require_doc(conn, ws_slug, doc_id)
            await _require_comment(conn, doc_id, comment_id)
            await conn.execute(
                "DELETE FROM comment_reaction WHERE comment_ref = $1 AND user_ref = $2",
                comment_id,
                user_id,
            )
            return await _comment_reaction_summary(conn, comment_id, user_id)
