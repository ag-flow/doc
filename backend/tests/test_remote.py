from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from docflow.remote import service as svc
from docflow.remote.schemas import (
    RemoteCertificateCreate,
    RemoteCertificateGenerate,
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


async def test_generate_certificate_returns_public_key_only(db_pool: asyncpg.Pool) -> None:
    cert = await svc.generate_certificate(
        db_pool,
        RemoteCertificateGenerate(slug="cert-gen", label="Generated"),
        _FERNET_KEY,
    )
    assert cert.slug == "cert-gen"
    assert cert.cert_type == "ssh_key"
    assert cert.public_part.startswith("ssh-ed25519 ")
    assert cert.fingerprint is not None
    assert not hasattr(cert, "private_key")
    assert not hasattr(cert, "private_enc")


async def test_generate_certificate_private_key_is_usable(db_pool: asyncpg.Pool) -> None:
    """La clé privée générée est stockée chiffrée et redéchiffrable — jamais renvoyée en clair."""
    await svc.generate_certificate(
        db_pool,
        RemoteCertificateGenerate(slug="cert-gen-rtt", label="Generated"),
        _FERNET_KEY,
    )
    private_key = await svc.get_certificate_private_key(db_pool, "cert-gen-rtt", _FERNET_KEY)
    assert "OPENSSH PRIVATE KEY" in private_key


async def test_generate_certificate_produces_distinct_keys(db_pool: asyncpg.Pool) -> None:
    a = await svc.generate_certificate(
        db_pool, RemoteCertificateGenerate(slug="cert-gen-a", label="A"), _FERNET_KEY
    )
    b = await svc.generate_certificate(
        db_pool, RemoteCertificateGenerate(slug="cert-gen-b", label="B"), _FERNET_KEY
    )
    assert a.public_part != b.public_part
    assert a.fingerprint != b.fingerprint


async def test_generate_certificate_duplicate_slug(db_pool: asyncpg.Pool) -> None:
    body = RemoteCertificateGenerate(slug="cert-gen-dup", label="Dup")
    await svc.generate_certificate(db_pool, body, _FERNET_KEY)
    with pytest.raises(HTTPException) as exc_info:
        await svc.generate_certificate(db_pool, body, _FERNET_KEY)
    assert exc_info.value.status_code == 409


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
        auth_secret="s3cr3t",
    )
    updated = await svc.update_point(db_pool, "pt-01", update, _FERNET_KEY)
    assert updated.label == "Updated"
    assert updated.username == "user2"
    assert updated.has_local_secret is True


async def test_update_point_blank_secret_keeps_existing(db_pool: asyncpg.Pool) -> None:
    """auth_secret omis (placeholder « laisser vide ») : ne doit PAS 422, garde le secret existant.

    Régression : RemotePointUpdate déléguait sa validation à RemotePointCreate, qui exige
    un auth_secret non vide pour auth_storage=local — rendant impossible, via l'API, le
    scénario que le formulaire promet explicitement (secret vide = inchangé).
    """
    await svc.create_point(db_pool, _point(), _FERNET_KEY)
    update = RemotePointUpdate(
        label="Updated",
        point_type="ftp",
        host="ftp.example.com",
        username="user",
        auth_type="password",
        auth_storage="local",
        auth_secret=None,
    )
    updated = await svc.update_point(db_pool, "pt-01", update, _FERNET_KEY)
    assert updated.label == "Updated"
    assert updated.has_local_secret is True
    secret = await svc.get_point_secret(db_pool, "pt-01", _FERNET_KEY)
    assert secret == "s3cr3t"


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


def test_point_accepts_bitbucket_provider() -> None:
    pt = RemotePointCreate(
        slug="bb-pt",
        label="Bitbucket",
        point_type="git",
        host="bitbucket.org",
        username="user",
        auth_type="pat",
        auth_storage="vault",
        auth_vault_ref="${vault://token}",
        git_provider="bitbucket",
        git_repo="team/repo",
    )
    assert pt.git_provider == "bitbucket"


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


# ── Validation Pydantic — RemotePointUpdate ──────────────────────────────────


def test_update_local_storage_does_not_require_secret() -> None:
    """Contrairement à Create, Update accepte un auth_secret omis (I-conservation)."""
    RemotePointUpdate(
        label="X",
        point_type="ftp",
        host="ftp.example.com",
        username="user",
        auth_type="password",
        auth_storage="local",
    )


def test_update_git_requires_provider() -> None:
    with pytest.raises(ValueError, match="git_provider"):
        RemotePointUpdate(
            label="Git",
            point_type="git",
            host="github.com",
            username="user",
            auth_type="pat",
            auth_storage="vault",
            auth_vault_ref="${vault://token}",
            git_repo="org/repo",
        )


def test_update_password_requires_auth_storage() -> None:
    with pytest.raises(ValueError, match="auth_storage"):
        RemotePointUpdate(
            label="X",
            point_type="ftp",
            host="ftp.example.com",
            username="user",
            auth_type="password",
        )


def test_update_certificate_requires_slug() -> None:
    with pytest.raises(ValueError, match="certificate_slug"):
        RemotePointUpdate(
            label="Cert",
            point_type="sftp",
            host="sftp.example.com",
            username="user",
            auth_type="certificate",
        )


async def test_generate_tls_certificate_self_signed(db_pool: asyncpg.Pool) -> None:
    """cert_type=tls : certificat X.509 auto-signé, clé privée chiffrée redéchiffrable."""
    cert = await svc.generate_certificate(
        db_pool,
        RemoteCertificateGenerate(
            slug="cert-tls", label="TLS", cert_type="tls", common_name="docflow-ftps"
        ),
        _FERNET_KEY,
    )
    assert cert.cert_type == "tls"
    assert cert.public_part.startswith("-----BEGIN CERTIFICATE-----")
    assert cert.expires_at is not None  # défaut : +10 ans
    assert not hasattr(cert, "private_key")

    from cryptography import x509
    from cryptography.x509.oid import NameOID

    parsed = x509.load_pem_x509_certificate(cert.public_part.encode())
    cns = parsed.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    assert cns[0].value == "docflow-ftps"
    assert parsed.issuer == parsed.subject  # auto-signé

    private_key = await svc.get_certificate_private_key(db_pool, "cert-tls", _FERNET_KEY)
    assert "PRIVATE KEY" in private_key


async def test_generate_tls_certificate_rejects_past_expiry(db_pool: asyncpg.Pool) -> None:
    from datetime import UTC, datetime

    with pytest.raises(HTTPException) as exc_info:
        await svc.generate_certificate(
            db_pool,
            RemoteCertificateGenerate(
                slug="cert-tls-past",
                label="TLS",
                cert_type="tls",
                expires_at=datetime(2020, 1, 1, tzinfo=UTC),
            ),
            _FERNET_KEY,
        )
    assert exc_info.value.status_code == 422


async def test_generate_ssh_key_with_comment(db_pool: asyncpg.Pool) -> None:
    """common_name = commentaire de la clé publique (repère dans authorized_keys)."""
    cert = await svc.generate_certificate(
        db_pool,
        RemoteCertificateGenerate(slug="cert-gen-comment", label="G", common_name="deploy@docflow"),
        _FERNET_KEY,
    )
    assert cert.public_part.startswith("ssh-ed25519 ")
    assert cert.public_part.endswith(" deploy@docflow")
    assert "\n" not in cert.public_part


def test_generate_common_name_single_line() -> None:
    with pytest.raises(ValueError):
        RemoteCertificateGenerate(slug="x-y", label="X", common_name="a\nb")
