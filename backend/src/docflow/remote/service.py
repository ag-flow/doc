from __future__ import annotations

import hashlib

import asyncpg
from fastapi import HTTPException

from docflow.crypto import decrypt_str, encrypt_str
from docflow.remote.schemas import (
    RemoteCertificateCreate,
    RemoteCertificateOut,
    RemotePointCreate,
    RemotePointOut,
    RemotePointUpdate,
)


def _fingerprint(public_part: str) -> str:
    return hashlib.sha256(public_part.encode()).hexdigest()[:16]


def _cert_row(row: asyncpg.Record) -> RemoteCertificateOut:
    return RemoteCertificateOut(**{k: v for k, v in dict(row).items() if k != "private_enc"})


def _point_row(row: asyncpg.Record) -> RemotePointOut:
    d = dict(row)
    has_local = d.pop("has_local_secret")
    d.pop("auth_secret_enc", None)
    return RemotePointOut(**d, has_local_secret=bool(has_local))


# ── Certificats ──────────────────────────────────────────────────────────────


async def list_certificates(pool: asyncpg.Pool) -> list[RemoteCertificateOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, slug, label, cert_type, public_part, fingerprint, expires_at, created_at"
            " FROM remote_certificate ORDER BY created_at"
        )
    return [_cert_row(r) for r in rows]


async def create_certificate(
    pool: asyncpg.Pool, body: RemoteCertificateCreate, fernet_key: str
) -> RemoteCertificateOut:
    private_enc = encrypt_str(fernet_key, body.private_key).encode()
    fp = _fingerprint(body.public_part)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO remote_certificate
                    (slug, label, cert_type, public_part, private_enc, fingerprint, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, slug, label, cert_type, public_part, fingerprint, expires_at,
                          created_at
                """,
                body.slug,
                body.label,
                body.cert_type,
                body.public_part,
                private_enc,
                fp,
                body.expires_at,
            )
        except asyncpg.UniqueViolationError as e:
            raise HTTPException(409, "slug de certificat déjà utilisé") from e
    assert row is not None
    return _cert_row(row)


async def get_certificate(pool: asyncpg.Pool, slug: str) -> RemoteCertificateOut:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, slug, label, cert_type, public_part, fingerprint, expires_at, created_at"
            " FROM remote_certificate WHERE slug = $1",
            slug,
        )
    if row is None:
        raise HTTPException(404, "certificat introuvable")
    return _cert_row(row)


async def get_certificate_private_key(pool: asyncpg.Pool, slug: str, fernet_key: str) -> str:
    """Retourne la clé privée déchiffrée — usage interne (worker backup) uniquement."""
    async with pool.acquire() as conn:
        enc = await conn.fetchval(
            "SELECT private_enc FROM remote_certificate WHERE slug = $1", slug
        )
    if enc is None:
        raise HTTPException(404, "certificat introuvable")
    return decrypt_str(fernet_key, enc.decode())


async def delete_certificate(pool: asyncpg.Pool, slug: str) -> None:
    async with pool.acquire() as conn:
        deleted = await conn.execute("DELETE FROM remote_certificate WHERE slug = $1", slug)
    if deleted == "DELETE 0":
        raise HTTPException(404, "certificat introuvable")


# ── Remote Points ─────────────────────────────────────────────────────────────

_POINT_SELECT = """
    SELECT id, slug, label, point_type, host, port, username,
           git_provider, git_repo, git_branch,
           auth_type, auth_storage, auth_vault_ref, certificate_slug,
           (auth_secret_enc IS NOT NULL) AS has_local_secret,
           created_at, updated_at
    FROM remote_point
"""


async def list_points(pool: asyncpg.Pool) -> list[RemotePointOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_POINT_SELECT + " ORDER BY created_at")
    return [_point_row(r) for r in rows]


async def create_point(
    pool: asyncpg.Pool, body: RemotePointCreate, fernet_key: str | None
) -> RemotePointOut:
    secret_enc: bytes | None = None
    if body.auth_storage == "local":
        if not fernet_key:
            raise HTTPException(
                422, "encryption_key non configurée — impossible de stocker le secret en local"
            )
        assert body.auth_secret is not None
        secret_enc = encrypt_str(fernet_key, body.auth_secret).encode()

    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO remote_point
                    (slug, label, point_type, host, port, username,
                     git_provider, git_repo, git_branch,
                     auth_type, auth_storage, auth_secret_enc, auth_vault_ref,
                     certificate_slug)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                RETURNING id, slug, label, point_type, host, port, username,
                          git_provider, git_repo, git_branch,
                          auth_type, auth_storage, auth_vault_ref, certificate_slug,
                          (auth_secret_enc IS NOT NULL) AS has_local_secret,
                          created_at, updated_at
                """,
                body.slug,
                body.label,
                body.point_type,
                body.host,
                body.port,
                body.username,
                body.git_provider,
                body.git_repo,
                body.git_branch,
                body.auth_type,
                body.auth_storage,
                secret_enc,
                body.auth_vault_ref,
                body.certificate_slug,
            )
        except asyncpg.UniqueViolationError as e:
            raise HTTPException(409, "slug de remote point déjà utilisé") from e
        except asyncpg.ForeignKeyViolationError as e:
            raise HTTPException(422, "certificate_slug introuvable") from e
    assert row is not None
    return _point_row(row)


async def get_point(pool: asyncpg.Pool, slug: str) -> RemotePointOut:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_POINT_SELECT + " WHERE slug = $1", slug)
    if row is None:
        raise HTTPException(404, "remote point introuvable")
    return _point_row(row)


async def update_point(
    pool: asyncpg.Pool, slug: str, body: RemotePointUpdate, fernet_key: str | None
) -> RemotePointOut:
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id, auth_secret_enc FROM remote_point WHERE slug = $1", slug
        )
        if existing is None:
            raise HTTPException(404, "remote point introuvable")

        # Calcule le secret à stocker
        secret_enc: bytes | None = None
        if body.auth_storage == "local":
            if body.auth_secret:
                if not fernet_key:
                    raise HTTPException(422, "encryption_key non configurée")
                secret_enc = encrypt_str(fernet_key, body.auth_secret).encode()
            else:
                # Pas de nouveau secret fourni → conserver l'existant
                secret_enc = existing["auth_secret_enc"]
        # auth_storage != 'local' → secret_enc reste None (colonne mise à NULL)

        try:
            row = await conn.fetchrow(
                """
                UPDATE remote_point SET
                    label=$2, point_type=$3, host=$4, port=$5, username=$6,
                    git_provider=$7, git_repo=$8, git_branch=$9,
                    auth_type=$10, auth_storage=$11, auth_vault_ref=$12,
                    certificate_slug=$13, auth_secret_enc=$14,
                    updated_at=now()
                WHERE slug=$1
                RETURNING id, slug, label, point_type, host, port, username,
                          git_provider, git_repo, git_branch,
                          auth_type, auth_storage, auth_vault_ref, certificate_slug,
                          (auth_secret_enc IS NOT NULL) AS has_local_secret,
                          created_at, updated_at
                """,
                slug,
                body.label,
                body.point_type,
                body.host,
                body.port,
                body.username,
                body.git_provider,
                body.git_repo,
                body.git_branch,
                body.auth_type,
                body.auth_storage,
                body.auth_vault_ref,
                body.certificate_slug,
                secret_enc,
            )
        except asyncpg.ForeignKeyViolationError as e:
            raise HTTPException(422, "certificate_slug introuvable") from e
    assert row is not None
    return _point_row(row)


async def delete_point(pool: asyncpg.Pool, slug: str) -> None:
    async with pool.acquire() as conn:
        deleted = await conn.execute("DELETE FROM remote_point WHERE slug = $1", slug)
    if deleted == "DELETE 0":
        raise HTTPException(404, "remote point introuvable")


async def get_point_secret(pool: asyncpg.Pool, slug: str, fernet_key: str) -> str:
    """Retourne le secret déchiffré — usage interne (worker backup) uniquement."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT auth_storage, auth_secret_enc, auth_vault_ref"
            " FROM remote_point WHERE slug = $1",
            slug,
        )
    if row is None:
        raise HTTPException(404, "remote point introuvable")
    if row["auth_storage"] == "local":
        enc = row["auth_secret_enc"]
        if enc is None:
            raise HTTPException(422, "aucun secret local stocké")
        return decrypt_str(fernet_key, enc.decode())
    if row["auth_storage"] == "vault":
        return str(row["auth_vault_ref"])  # la résolution vault est faite par l'appelant
    raise HTTPException(422, "auth par certificat — pas de secret textuel")
