"""Garde-fou SSRF pour les fetch serveur vers des URLs administrées.

Toute requête HTTP sortante dont l'URL est fournie par un utilisateur (webhooks,
automations, contrats OpenAPI, sources de galerie de templates) doit passer par
`validate_public_url` AVANT d'être émise.

Politique (version conservatrice) : seuls `http`/`https` vers des adresses
**publiques** sont autorisés. On résout l'hôte et on refuse toute résolution
tombant sur une plage privée / loopback / link-local (dont 169.254.169.254 des
métadonnées cloud) / multicast / réservée / non spécifiée.

Limite connue (documentée) : la validation résout l'hôte puis laisse httpx
ré-résoudre lors de la requête ; une attaque DNS-rebinding pourrait théoriquement
renvoyer une IP publique à la validation et une IP interne à la requête. Fermer
totalement cette fenêtre imposerait d'épingler l'IP validée dans un transport
httpx custom (et de casser la vérification TLS par nom d'hôte) — hors périmètre
de ce durcissement. La parade complémentaire retenue est de **ne pas suivre les
redirections** sur les fetch concernés, la cible connectée restant l'hôte validé.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})

_IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class SSRFError(ValueError):
    """URL sortante refusée par la politique anti-SSRF."""


def is_blocked_ip(ip: _IpAddress) -> bool:
    """Vrai si l'adresse vise le réseau interne / des plages non routables publiquement."""
    # Déballe une éventuelle IPv4 encapsulée en IPv6 (::ffff:169.254.169.254).
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            ip = mapped
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _resolve(host: str) -> list[_IpAddress]:
    # Une IP littérale est validée telle quelle (pas de résolution DNS).
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise SSRFError(f"hôte non résolu : {host}") from exc

    addrs: list[_IpAddress] = []
    for info in infos:
        sockaddr = info[4]
        addrs.append(ipaddress.ip_address(sockaddr[0]))
    if not addrs:
        raise SSRFError(f"hôte non résolu : {host}")
    return addrs


async def validate_public_url(url: str) -> None:
    """Valide une URL sortante ; lève `SSRFError` si elle est refusée.

    À appeler juste avant tout fetch dont l'URL est administrée par un
    utilisateur, et à ré-appeler sur la cible d'une éventuelle redirection.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise SSRFError(f"schéma non autorisé : {scheme or '(vide)'} (http/https requis)")

    host = parsed.hostname
    if not host:
        raise SSRFError("URL sans hôte")

    for ip in await _resolve(host):
        if is_blocked_ip(ip):
            raise SSRFError(f"hôte non autorisé (adresse interne/non publique) : {host}")
