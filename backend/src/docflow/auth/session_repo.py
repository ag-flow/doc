"""Accès base aux sessions serveur (table `user_sessions`).

Repris de l'implémentation de référence a2a (`repositories/sessions.py`). Cette
couche ne fait QUE lire/écrire : la politique d'expiration (inactivité glissante
+ plafond absolu) est une décision qui vit dans `auth/sessions.py`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg


async def create(conn: asyncpg.Connection, *, user_id: UUID, token_hash: str) -> asyncpg.Record:
    record = await conn.fetchrow(
        """
        INSERT INTO user_sessions (user_id, token_hash)
        VALUES ($1, $2)
        RETURNING *
        """,
        user_id,
        token_hash,
    )
    assert record is not None
    return record


async def get_active_by_hash(
    conn: asyncpg.Connection, token_hash: str
) -> asyncpg.Record | None:
    """Session non révoquée portant cette empreinte.

    Ne juge PAS l'expiration : les deux échéances sont une décision de politique
    (`auth/sessions.py`). Ici on ne fait que lire.
    """
    return await conn.fetchrow(
        "SELECT * FROM user_sessions WHERE token_hash = $1 AND revoked_at IS NULL",
        token_hash,
    )


async def touch(conn: asyncpg.Connection, session_id: UUID, *, seen_at: datetime) -> None:
    """Fait glisser la fenêtre d'inactivité. `auth_time` n'est jamais touché —
    c'est ce qui rend le plafond absolu inéluctable."""
    await conn.execute(
        "UPDATE user_sessions SET last_seen_at = $2 WHERE id = $1", session_id, seen_at
    )


async def revoke_by_hash(conn: asyncpg.Connection, token_hash: str, *, at: datetime) -> None:
    await conn.execute(
        "UPDATE user_sessions SET revoked_at = $2 WHERE token_hash = $1 AND revoked_at IS NULL",
        token_hash,
        at,
    )


async def revoke_all_for_user(conn: asyncpg.Connection, user_id: UUID, *, at: datetime) -> int:
    """Révoque toutes les sessions actives d'un utilisateur. Rend le nombre de
    sessions coupées — un administrateur qui révoque veut savoir ce qu'il a
    coupé, et zéro est une information utile."""
    revoked = await conn.fetch(
        """
        UPDATE user_sessions SET revoked_at = $2
        WHERE user_id = $1 AND revoked_at IS NULL
        RETURNING id
        """,
        user_id,
        at,
    )
    return len(revoked)


async def list_active_for_user(
    conn: asyncpg.Connection, user_id: UUID
) -> list[asyncpg.Record]:
    return list(
        await conn.fetch(
            """
            SELECT id, auth_time, last_seen_at, created_at
            FROM user_sessions
            WHERE user_id = $1 AND revoked_at IS NULL
            ORDER BY last_seen_at DESC
            """,
            user_id,
        )
    )


async def delete_expired(conn: asyncpg.Connection, *, older_than: datetime) -> int:
    """Purge les lignes dont plus rien ne peut dépendre : révoquées ou inactives
    depuis plus longtemps que le plafond absolu. Sans elle, la table ne fait que
    croître — une session morte n'a aucune valeur d'audit."""
    deleted = await conn.fetch(
        """
        DELETE FROM user_sessions
        WHERE last_seen_at < $1 OR (revoked_at IS NOT NULL AND revoked_at < $1)
        RETURNING id
        """,
        older_than,
    )
    return len(deleted)
