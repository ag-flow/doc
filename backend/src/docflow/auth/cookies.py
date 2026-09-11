"""Pose et retrait du cookie de session — repris de la référence a2a
(`auth/common.py`).

La pose est asynchrone : la session vit en base (c'est ce qui la rend
révocable), donc l'ouvrir demande une connexion.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import Response

from docflow.auth.sessions import issue_session_token, session_cookie_name


async def set_session_cookie(
    response: Response,
    conn: asyncpg.Connection,
    user_id: UUID,
    *,
    secure: bool,
    max_age: int,
) -> None:
    """Ouvre une session et pose le cookie HttpOnly. `max_age` = fenêtre
    d'inactivité côté navigateur ; le plafond absolu est vérifié en base."""
    response.set_cookie(
        key=session_cookie_name(),
        value=await issue_session_token(conn, user_id),
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=secure,
    )


def delete_session_cookie(response: Response, *, secure: bool) -> None:
    """Retire le cookie avec EXACTEMENT les mêmes attributs que la pose :
    `Secure`/`SameSite` divergents entre pose et suppression, et un navigateur
    peut refuser d'appliquer la suppression (« Leave Secure Cookies Alone ») —
    le cookie survivrait côté client alors que la session est déjà révoquée."""
    response.delete_cookie(
        key=session_cookie_name(),
        httponly=True,
        samesite="lax",
        secure=secure,
    )
