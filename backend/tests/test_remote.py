from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from docflow.remote import service as svc
from docflow.remote.schemas import (
    RemoteCertificateCreate,
    RemotePointCreate,
    RemotePointUpdate,
)

_FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
async def _clean(db_pool: asyncpg.Pool) -> AsyncIterator[None]:
    yield
    await db_pool.execute("DELETE FROM remote_point")
    await db_pool.execute("DELETE FROM remote_certificate")


# ── helpers ───────────────────────────────────────────────────────────────────


def _cert(slug: str = "cert-01") -> RemoteCertificateCreate:
    return RemoteCertificateCreate(
        slug=slug,
        label="Test Cert",
        cert_type="ssh_key",
        public_part="ssh-rsa AAAA...",
        private_key="-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----",
    )


def _point(slug: str = "pt-01") -> RemotePointCreate:
    return RemotePointCreate(
        slug=slug,
        label="Test FTP Point",
        point_type="ftp",
        host="ftp.example.com",
        username="user",
        auth_type="password",
        auth_storage="local",
        auth_secret="s3cr3t",
    )


# ── Certificats ───────────────────────────────────────────────────────────────


async def test_create_certificate(db_pool: asyncpg.Pool) -> None:
    cert = await svc.create_certificate(db_pool, _cert(), _FERNET_KEY)
    assert cert.slug == "cert-01"
    assert cert.cert_type == "ssh_key"
    assert cert.fingerprint is not None


async def test_create_certificate_duplicate_slug(db_pool: asyncpg.Pool) -> None:
    await svc.create_certificate(db_pool, _cert(), _FERNET_KEY)
    with pytest.raises(HTTPException) as exc_info:
        await svc.create_certificate(db_pool, _cert(), _FERNET_KEY)
    assert exc_info.value.status_code == 409


async def test_get_certificate(db_pool: asyncpg.Pool) -> None:
    await svc.create_certificate(db_pool, _cert(), _FERNET_KEY)
    cert = await svc.get_certificate(db_pool, "cert-01")
    assert cert.slug == "cert-01"


async def test_get_certificate_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await svc.get_certificate(db_pool, "missing")
    assert exc_info.value.status_code == 404


async def test_get_certificate_private_key_round_trip(db_pool: asyncpg.Pool) -> None:
    """La clé privée chiffrée à l'écriture doit être restituée à l'identique."""
    original = "-----BEGIN EC PRIVATE KEY-----\nsecret\n-----END EC PRIVATE KEY-----"
    body = RemoteCertificateCreate(
        slug="cert-rtt",
        label="RTT",
        cert_type="tls",
        public_part="cert-pem-here",
        private_key=original,
    )
    await svc.create_certificate(db_pool, body, _FERNET_KEY)
    retrieved = await svc.get_certificate_private_key(db_pool, "cert-rtt", _FERNET_KEY)
    assert retrieved == original


async def test_get_certificate_private_key_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await svc.get_certificate_private_key(db_pool, "missing", _FERNET_KEY)
    assert exc_info.value.status_code == 404


async def test_delete_certificate(db_pool: asyncpg.Pool) -> None:
    await svc.create_certificate(db_pool, _cert(), _FERNET_KEY)
    await svc.delete_certificate(db_pool, "cert-01")
    with pytest.raises(HTTPException) as exc_info:
        await svc.get_certificate(db_pool, "cert-01")
    assert exc_info.value.status_code == 404


async def test_delete_certificate_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await svc.delete_certificate(db_pool, "missing")
    assert exc_info.value.status_code == 404


async def test_list_certificates(db_pool: asyncpg.Pool) -> None:
    await svc.create_certificate(db_pool, _cert("cert-aa"), _FERNET_KEY)
    await svc.create_certificate(db_pool, _cert("cert-bb"), _FERNET_KEY)
    certs = await svc.list_certificates(db_pool)
    slugs = {c.slug for c in certs}
    assert {"cert-aa", "cert-bb"} <= slugs


# ── Remote Points ─────────────────────────────────────────────────────────────


async def test_create_point_local_password(db_pool: asyncpg.Pool) -> None:
    pt = await svc.create_point(db_pool, _point(), _FERNET_KEY)
    assert pt.slug == "pt-01"
    assert pt.point_type == "ftp"
    assert pt.has_local_secret is True


async def test_create_point_vault(db_pool: asyncpg.Pool) -> None:
    body = RemotePointCreate(
        slug="pt-vault",
        label="Vault Point",
        point_type="ftps",
        host="ftp.example.com",
        username="user",
        auth_type="pat",
        auth_storage="vault",
        auth_vault_ref="${vault://my/secret}",
    )
    pt = await svc.create_point(db_pool, body, _FERNET_KEY)
    assert pt.has_local_secret is False
    assert pt.auth_vault_ref == "${vault://my/secret}"


async def test_create_point_duplicate_slug(db_pool: asyncpg.Pool) -> None:
    await svc.create_point(db_pool, _point(), _FERNET_KEY)
    with pytest.raises(HTTPException) as exc_info:
        await svc.create_point(db_pool, _point(), _FERNET_KEY)
    assert exc_info.value.status_code == 409


async def test_get_point(db_pool: asyncpg.Pool) -> None:
    await svc.create_point(db_pool, _point(), _FERNET_KEY)
    pt = await svc.get_point(db_pool, "pt-01")
    assert pt.slug == "pt-01"


async def test_get_point_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await svc.get_point(db_pool, "missing")
    assert exc_info.value.status_code == 404


async def test_update_point_label_only(db_pool: asyncpg.Pool) -> None:
    """Mettre à jour le label sans changer le secret : fournir à nouveau le secret."""
    await svc.create_point(db_pool, _point(), _FERNET_KEY)
    update = RemotePointUpdate(
        label="Updated",
        point_type="ftp",
        host="ftp.example.com",
        username="user2",
        auth_type="password",
        auth_storage="local",
        auth_secret="s3cr3t",  # reprécisé, Pydantic l'exige pour auth_storage=local
    )
    updated = await svc.update_point(db_pool, "pt-01", update, _FERNET_KEY)
    assert updated.label == "Updated"
    assert updated.username == "user2"
    assert updated.has_local_secret is True


async def test_update_point_replaces_secret(db_pool: asyncpg.Pool) -> None:
    await svc.create_point(db_pool, _point(), _FERNET_KEY)
    update = RemotePointUpdate(
        label="Updated",
        point_type="ftp",
        host="ftp.example.com",
        username="user",
        auth_type="password",
        auth_storage="local",
        auth_secret="nouveau-secret",
    )
    await svc.update_point(db_pool, "pt-01", update, _FERNET_KEY)
    secret = await svc.get_point_secret(db_pool, "pt-01", _FERNET_KEY)
    assert secret == "nouveau-secret"


async def test_delete_point(db_pool: asyncpg.Pool) -> None:
    await svc.create_point(db_pool, _point(), _FERNET_KEY)
    await svc.delete_point(db_pool, "pt-01")
    with pytest.raises(HTTPException) as exc_info:
        await svc.get_point(db_pool, "pt-01")
    assert exc_info.value.status_code == 404


async def test_delete_point_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await svc.delete_point(db_pool, "missing")
    assert exc_info.value.status_code == 404


async def test_list_points(db_pool: asyncpg.Pool) -> None:
    await svc.create_point(db_pool, _point("pt-aa"), _FERNET_KEY)
    await svc.create_point(db_pool, _point("pt-bb"), _FERNET_KEY)
    pts = await svc.list_points(db_pool)
    slugs = {p.slug for p in pts}
    assert {"pt-aa", "pt-bb"} <= slugs


# ── Validation Pydantic ───────────────────────────────────────────────────────


def test_point_git_requires_provider() -> None:
    with pytest.raises(ValueError, match="git_provider"):
        RemotePointCreate(
            slug="git-pt",
            label="Git",
            point_type="git",
            host="github.com",
            username="user",
            auth_type="pat",
            auth_storage="vault",
            auth_vault_ref="${vault://token}",
            git_repo="org/repo",
        )


def test_point_password_requires_auth_storage() -> None:
    with pytest.raises(ValueError, match="auth_storage"):
        RemotePointCreate(
            slug="pt-xx",
            label="X",
            point_type="ftp",
            host="ftp.example.com",
            username="user",
            auth_type="password",
        )


def test_point_local_storage_requires_secret() -> None:
    with pytest.raises(ValueError, match="auth_secret"):
        RemotePointCreate(
            slug="pt-xx",
            label="X",
            point_type="ftp",
            host="ftp.example.com",
            username="user",
            auth_type="password",
            auth_storage="local",
        )


def test_point_certificate_requires_slug() -> None:
    with pytest.raises(ValueError, match="certificate_slug"):
        RemotePointCreate(
            slug="pt-cert",
            label="Cert",
            point_type="sftp",
            host="sftp.example.com",
            username="user",
            auth_type="certificate",
        )
