"""Sessions serveur opaques et révocables (IHM humaine).

Le cookie ne porte que **256 bits d'aléa** : rien n'en est déductible, il ne
prouve rien par lui-même. Toute la décision vit en base — donc elle est
révocable, immédiatement et réellement.

Deux échéances, et il faut les deux :

- **inactivité glissante** (`last_seen_at`), qui ferme les sessions oubliées ;
- **plafond absolu** depuis `auth_time`, indépendant de l'activité, qui force une
  réauthentification périodique. Sans lui, une session active en permanence ne se
  referme jamais et aucune ré-évaluation des droits n'est jamais forcée.

Remplacement du jeton HS256 de `auth/jwt.py` pour l'IHM. Repris de
l'implémentation de référence a2a (`auth/sessions.py`). Écart docflow assumé :
`jwt_secret` n'est PAS supprimé (il signe encore les liens d'artefacts, la
preview et le backup) ; seul le jeton de session migre.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import structlog

from docflow.auth import session_repo

log = structlog.get_logger(__name__)

SESSION_COOKIE_NAME = "docflow_session"
# 32 octets = 256 bits d'entropie ; token_urlsafe encode en une chaîne plus
# longue, ce qui n'ajoute pas d'entropie mais ne coûte rien.
_TOKEN_BYTES = 32


def session_cookie_name() -> str:
    return SESSION_COOKIE_NAME


def hash_session_token(token: str) -> str:
    """SHA-256, comme les clés API et les tickets d'upload. Pas d'argon2 : le
    jeton est une valeur à haute entropie générée par le serveur, pas un mot de
    passe humain — il n'y a pas de dictionnaire à ralentir."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_session_token(conn: asyncpg.Connection, user_id: UUID) -> str:
    """Ouvre une session et rend le jeton EN CLAIR, seule et unique fois.

    Un nouvel identifiant est émis à chaque login, même si une session existe
    déjà : protection contre la fixation de session.
    """
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    record = await session_repo.create(
        conn, user_id=user_id, token_hash=hash_session_token(token)
    )
    log.info("session_opened", user_id=str(user_id), session_id=str(record["id"]))
    return token


async def resolve_session_user_id(
    conn: asyncpg.Connection,
    token: str,
    *,
    idle_ttl_seconds: int,
    absolute_ttl_seconds: int,
) -> UUID | None:
    """Rend l'utilisateur d'une session vivante, ou None.

    Fail closed : toute session absente, révoquée, inactive au-delà de la
    fenêtre ou plus vieille que le plafond absolu rend None. Une session expirée
    par l'une ou l'autre échéance est révoquée au passage — sinon elle resterait
    « active » en base et fausserait la vue d'administration.
    """
    now = datetime.now(UTC)

    session = await session_repo.get_active_by_hash(conn, hash_session_token(token))
    if session is None:
        return None

    if now - session["last_seen_at"] > timedelta(seconds=idle_ttl_seconds):
        log.info("session_expired", session_id=str(session["id"]), reason="idle")
        await session_repo.revoke_by_hash(conn, session["token_hash"], at=now)
        return None

    if now - session["auth_time"] > timedelta(seconds=absolute_ttl_seconds):
        log.info("session_expired", session_id=str(session["id"]), reason="absolute_cap")
        await session_repo.revoke_by_hash(conn, session["token_hash"], at=now)
        return None

    await session_repo.touch(conn, session["id"], seen_at=now)
    user_id: UUID = session["user_id"]
    return user_id


async def revoke_session(conn: asyncpg.Connection, token: str) -> None:
    """Déconnexion : la ligne est révoquée, pas seulement le cookie retiré. C'est
    ce qui fait qu'un jeton copié avant la déconnexion cesse de valoir."""
    await session_repo.revoke_by_hash(conn, hash_session_token(token), at=datetime.now(UTC))


async def revoke_all_sessions_for_user(conn: asyncpg.Connection, user_id: UUID) -> int:
    revoked = await session_repo.revoke_all_for_user(conn, user_id, at=datetime.now(UTC))
    log.info("sessions_revoked", user_id=str(user_id), count=revoked)
    return revoked
