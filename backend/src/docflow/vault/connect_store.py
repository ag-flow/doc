"""État éphémère du parcours « Connecter à Harpocrate » (table `connect_flow`).

Entre le lancement (`start`) et le retour navigateur (`callback`), le serveur
doit retenir un `ConnectState` (code_verifier + clé privée EC P-256 éphémère)
SANS jamais l'exposer au navigateur. Ce module ne chiffre JAMAIS lui-même :
il persiste des blobs déjà chiffrés (`*_enc`, Fernet via `docflow.crypto`)
fournis par l'appelant (chiffrement/déchiffrement réel : Task C). Il ne
détient donc pas la clé — il manipule des chaînes opaques.

`state` (le paramètre renvoyé par le navigateur au callback) n'est jamais
stocké en clair : seule son empreinte sha256 (`state_hash`) sert de clé de
lookup, comme `upload_id_hash` pour les tickets d'upload (migration 0065).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import TypeAlias

import asyncpg

#: Connexion directe ou pool — les deux exposent la même API fetchrow/execute.
Connectable: TypeAlias = asyncpg.Pool | asyncpg.Connection


def _hash_state(state: str) -> str:
    """Empreinte de stockage du `state` (jamais le clair en base)."""
    return hashlib.sha256(state.encode()).hexdigest()


async def put(
    conn: Connectable,
    *,
    state: str,
    owner_id: uuid.UUID,
    state_blob_enc: str,
    pending_enc: str,
    expires_at: datetime,
) -> None:
    """Enregistre un `ConnectState` éphémère, lié à son propriétaire et à un TTL.

    `state_blob_enc` et `pending_enc` sont déjà chiffrés par l'appelant :
    ce module ne fait que les ranger opaques.
    """
    await conn.execute(
        """
        INSERT INTO connect_flow (state_hash, owner_ref, state_enc, pending_enc, expires_at)
        VALUES ($1, $2, $3, $4, $5)
        """,
        _hash_state(state),
        owner_id,
        state_blob_enc,
        pending_enc,
        expires_at,
    )


async def take_active(
    conn: Connectable,
    *,
    state: str,
    owner_id: uuid.UUID,
    now: datetime,
) -> asyncpg.Record | None:
    """Lit la ligne active pour `state` SANS la consommer.

    « Active » = non expirée, non consommée, ET appartenant à `owner_id` —
    l'isolation par propriétaire empêche qu'un `state` capturé par un tiers
    livre l'état d'un autre utilisateur. Ne pose jamais `consumed_at` :
    l'appelant décide quand marquer la consommation (`mark_consumed`).
    """
    return await conn.fetchrow(
        """
        SELECT state_enc, pending_enc
        FROM connect_flow
        WHERE state_hash = $1
          AND owner_ref = $2
          AND consumed_at IS NULL
          AND expires_at > $3
        """,
        _hash_state(state),
        owner_id,
        now,
    )


async def mark_consumed(conn: Connectable, *, state: str, now: datetime) -> None:
    """Marque la ligne `state` consommée (usage unique)."""
    await conn.execute(
        "UPDATE connect_flow SET consumed_at = $2 WHERE state_hash = $1",
        _hash_state(state),
        now,
    )


async def delete_expired(conn: Connectable, *, now: datetime) -> int:
    """Supprime les lignes expirées. Retourne le nombre de lignes supprimées.

    `now` est injecté (pas `now()` côté SQL) pour rester testable sans
    dépendre de l'horloge murale.
    """
    result = await conn.execute("DELETE FROM connect_flow WHERE expires_at <= $1", now)
    return int(result.split()[-1])
