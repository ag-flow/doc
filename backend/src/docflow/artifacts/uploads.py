"""Tickets d'upload d'artefact — upload en deux temps (create_upload → PUT → create_artifact).

Un agent qui détient déjà un fichier sur son disque ne peut ni le *streamer*
inline (data_base64 : coût de tokens, risque d'altération) ni pointer une URL
déjà publiée (source_url). Ce module fournit la troisième voie :

  1. `create_upload`  — délivre un ticket au porteur (`upload_id`) + une
     `upload_url` ; ne crée AUCUN artefact.
  2. `store_upload`   — appelé par le PUT REST : vérifie la taille annoncée,
     l'extension au registre et recalcule l'empreinte AVANT de ranger les octets.
  3. `consume_upload` — appelé par `create_artifact(upload_id)` : crée l'artefact
     complet (dédup sha256) et consomme le ticket (usage unique), le tout dans
     une seule transaction.

`upload_id` est une capacité au porteur : aléatoire (≥128 bits), jamais stocké
en clair (sha256), à usage unique, lié au workspace ET à l'utilisateur qui l'a
demandé, expirant sous un TTL court.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid

import asyncpg
from fastapi import HTTPException

from docflow.artifacts import service
from docflow.artifacts.media_types import load_allowed_map
from docflow.db.helpers import require_workspace
from docflow.schemas.artifact import ArtifactCreatedOut

_SHA256_RE_LEN = 64


def _hash_upload_id(upload_id: str) -> str:
    """Empreinte de stockage du secret porteur (jamais le clair en base)."""
    return hashlib.sha256(upload_id.encode()).hexdigest()


def _normalize_sha256(raw: str) -> str:
    value = raw.strip().lower()
    if len(value) != _SHA256_RE_LEN or not all(c in "0123456789abcdef" for c in value):
        raise HTTPException(status_code=422, detail="sha256 invalide (64 caractères hexadécimaux)")
    return value


async def create_upload(
    pool: asyncpg.Pool,
    ws_slug: str,
    *,
    filename: str,
    size_bytes: int,
    sha256: str,
    requested_by: uuid.UUID | None,
    ttl_seconds: int,
    max_bytes: int,
) -> dict[str, object]:
    """Crée un ticket d'upload et retourne {upload_id, expires_at, extension}.

    L'extension est validée EN AMONT au registre (échec rapide, avant tout
    octet) ; la taille annoncée est bornée. Aucun artefact n'est créé ici.
    """
    declared_sha = _normalize_sha256(sha256)
    if size_bytes <= 0:
        raise HTTPException(status_code=422, detail="size_bytes doit être strictement positif")
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"taille annoncée trop volumineuse ({size_bytes} octets, max {max_bytes})",
        )

    async with pool.acquire() as conn:
        # Validation d'extension au registre (source de vérité administrable) —
        # rejet immédiat, avant même de délivrer le ticket.
        allowed = await load_allowed_map(conn)
        name, ext, _media_type = service._validate_filename(filename, allowed)
        wk = await require_workspace(conn, ws_slug, allow_archived=False)

        # Capacité au porteur : 32 octets d'entropie (≫ 128 bits), jamais
        # dérivée du nom de fichier ni d'un compteur. Le clair n'est renvoyé
        # qu'ici, une seule fois ; la base ne garde que son empreinte.
        upload_id = secrets.token_urlsafe(32)
        row = await conn.fetchrow(
            """
            INSERT INTO upload_ticket
                (upload_id_hash, workspace_technical_key, requested_by, filename,
                 extension, declared_size_bytes, declared_sha256, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, now() + make_interval(secs => $8))
            RETURNING expires_at
            """,
            _hash_upload_id(upload_id),
            wk,
            requested_by,
            name,
            ext,
            size_bytes,
            declared_sha,
            ttl_seconds,
        )
    assert row is not None
    return {"upload_id": upload_id, "expires_at": row["expires_at"], "extension": ext}


async def store_upload(
    pool: asyncpg.Pool,
    upload_id: str,
    data: bytes,
    *,
    max_bytes: int,
) -> dict[str, object]:
    """Range les octets d'un ticket (étape PUT). Vérifie tout AVANT de stocker.

    Rejette : ticket inconnu/expiré/consommé (404), taille ≠ annoncée ou au-delà
    du plafond (413/422), extension retirée du registre entre-temps (422),
    empreinte recalculée ≠ annoncée (422). Un rejet ne range aucun octet.
    """
    if not data:
        raise HTTPException(status_code=422, detail="corps vide")
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"fichier trop volumineux ({len(data)} octets, max {max_bytes})",
        )

    async with pool.acquire() as conn:
        async with conn.transaction():
            ticket = await conn.fetchrow(
                """
                SELECT id, extension, declared_size_bytes, declared_sha256,
                       consumed_at, expires_at <= now() AS expired
                FROM upload_ticket
                WHERE upload_id_hash = $1
                FOR UPDATE
                """,
                _hash_upload_id(upload_id),
            )
            if ticket is None:
                raise HTTPException(status_code=404, detail="ticket d'upload introuvable")
            if ticket["consumed_at"] is not None:
                raise HTTPException(status_code=409, detail="ticket d'upload déjà consommé")
            if ticket["expired"]:
                raise HTTPException(status_code=404, detail="ticket d'upload expiré")

            if len(data) != ticket["declared_size_bytes"]:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"taille reçue ({len(data)} octets) différente de l'annonce "
                        f"({ticket['declared_size_bytes']})"
                    ),
                )
            # Re-validation d'extension au registre : il a pu changer depuis
            # create_upload — le refus doit tomber à l'étape PUT, pas seulement
            # à la création finale de l'artefact.
            allowed = await load_allowed_map(conn)
            if ticket["extension"] not in allowed:
                raise HTTPException(
                    status_code=422,
                    detail=f"extension '{ticket['extension']}' non autorisée",
                )
            actual_sha = hashlib.sha256(data).hexdigest()
            if actual_sha != ticket["declared_sha256"]:
                raise HTTPException(
                    status_code=422,
                    detail="empreinte sha256 reçue différente de l'annonce",
                )

            await conn.execute(
                "UPDATE upload_ticket SET data = $2, uploaded_at = now() WHERE id = $1",
                ticket["id"],
                data,
            )
    return {"size_bytes": len(data), "sha256": actual_sha}


async def consume_upload(
    pool: asyncpg.Pool,
    ws_slug: str,
    upload_id: str,
    *,
    requested_by: uuid.UUID | None,
    created_by: uuid.UUID | None,
    max_bytes: int,
) -> ArtifactCreatedOut:
    """Crée l'artefact depuis un ticket puis le consomme (usage unique), en une
    transaction atomique. L'artefact naît complet ou n'existe pas du tout.

    Vérifie l'appartenance au workspace ET l'identité demandeuse ; recalcule
    l'empreinte des octets stockés avant création.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            ticket = await conn.fetchrow(
                """
                SELECT id, workspace_technical_key, requested_by, filename,
                       declared_sha256, data, uploaded_at, consumed_at,
                       expires_at <= now() AS expired
                FROM upload_ticket
                WHERE upload_id_hash = $1
                FOR UPDATE
                """,
                _hash_upload_id(upload_id),
            )
            if ticket is None:
                raise HTTPException(status_code=404, detail="ticket d'upload introuvable")
            if ticket["consumed_at"] is not None:
                raise HTTPException(status_code=409, detail="ticket d'upload déjà consommé")
            if ticket["expired"]:
                raise HTTPException(status_code=404, detail="ticket d'upload expiré")

            # Le ticket est lié au workspace ET à l'utilisateur qui l'a demandé.
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            if ticket["workspace_technical_key"] != wk:
                raise HTTPException(status_code=404, detail="ticket d'upload d'un autre workspace")
            if ticket["requested_by"] != requested_by:
                raise HTTPException(
                    status_code=403,
                    detail="ticket d'upload lié à un autre utilisateur",
                )

            if ticket["uploaded_at"] is None or not ticket["data"]:
                raise HTTPException(
                    status_code=409,
                    detail="aucun octet reçu pour ce ticket (PUT manquant)",
                )
            data = bytes(ticket["data"])
            if hashlib.sha256(data).hexdigest() != ticket["declared_sha256"]:
                # Défense en profondeur : les octets stockés doivent toujours
                # correspondre à l'empreinte annoncée (déjà vérifiée au PUT).
                raise HTTPException(
                    status_code=422, detail="empreinte des octets stockés incohérente"
                )

            created = await service.insert_artifact(
                conn,
                ws_slug,
                filename=ticket["filename"],
                data=data,
                created_by=created_by,
                max_bytes=max_bytes,
            )
            # Usage unique : consommé et blob temporaire libéré, dans la même
            # transaction que la création — jamais d'artefact sans consommation,
            # ni de consommation sans artefact.
            await conn.execute(
                "UPDATE upload_ticket SET consumed_at = now(), data = NULL WHERE id = $1",
                ticket["id"],
            )
    return created


async def purge_expired(pool: asyncpg.Pool) -> int:
    """Supprime les tickets expirés (et leur blob temporaire). Retourne le nombre purgé."""
    result = await pool.execute("DELETE FROM upload_ticket WHERE expires_at < now()")
    return int(result.split()[-1])
