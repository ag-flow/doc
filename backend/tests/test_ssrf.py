from __future__ import annotations

import ipaddress

import pytest

from docflow.net.ssrf import SSRFError, is_blocked_ip, validate_public_url

# ── is_blocked_ip ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.1",  # privé
        "172.16.5.4",  # privé
        "192.168.1.1",  # privé
        "169.254.169.254",  # link-local (métadonnées cloud)
        "0.0.0.0",  # non spécifié
        "::1",  # loopback IPv6
        "fc00::1",  # unique local IPv6
        "fe80::1",  # link-local IPv6
        "::ffff:169.254.169.254",  # IPv4-mapped vers link-local
    ],
)
def test_is_blocked_ip_internal(ip: str) -> None:
    assert is_blocked_ip(ipaddress.ip_address(ip)) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700::1"])
def test_is_blocked_ip_public(ip: str) -> None:
    assert is_blocked_ip(ipaddress.ip_address(ip)) is False


# ── validate_public_url : schémas ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "file:///etc/passwd",
        "gopher://example.com",
        "//example.com/x",  # sans schéma
    ],
)
async def test_validate_rejects_non_http_scheme(url: str) -> None:
    with pytest.raises(SSRFError):
        await validate_public_url(url)


async def test_validate_rejects_missing_host() -> None:
    with pytest.raises(SSRFError):
        await validate_public_url("http://")


# ── validate_public_url : IP littérales internes (aucune résolution DNS) ─────────


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://127.0.0.1:8080/admin",
        "http://10.0.0.5/internal",
        "http://192.168.1.1",
        "http://[::1]/",
        "http://[::ffff:169.254.169.254]/",
    ],
)
async def test_validate_rejects_internal_ip_literals(url: str) -> None:
    with pytest.raises(SSRFError):
        await validate_public_url(url)


# ── validate_public_url : IP publiques littérales acceptées ──────────────────────


@pytest.mark.parametrize("url", ["http://8.8.8.8/", "https://1.1.1.1:443/path"])
async def test_validate_accepts_public_ip_literals(url: str) -> None:
    await validate_public_url(url)  # ne lève pas
