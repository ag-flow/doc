"""Signeur OBO sortant : identité de l'acteur posée sur l'appel d'un automate.

Mirroir volontaire de `rag.auth.obo.sign_actor` (contrat OBO v6, GUID-only) :
même charge canonique, même algorithme — mais SANS importer `rag`, couplage
interdit entre projets voisins (CLAUDE.md). Une divergence future du contrat
amont devra être répercutée ici à la main ; c'est le prix assumé de
l'indépendance de dépôt.

Sécurité-critique : ni le secret (clé servant à la signature HMAC) ni la
signature produite ne doivent jamais apparaître dans un journal.
"""

from __future__ import annotations

import hashlib
import hmac
import time

_BEARER_PREFIX = "Bearer "


def sign_actor(actor: str, timestamp: int, secret: str) -> str:
    """HMAC-SHA256 hex de `f"{actor}\\n{timestamp}"`, clé = `secret`.

    Charge canonique identique au vérificateur ingress (`mcp/obo.py`,
    `verify_actor`) : c'est la même recette appliquée dans l'autre sens.
    """
    payload = f"{actor}\n{timestamp}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def obo_headers(actor: str, secret: str, *, now: float | None = None) -> dict[str, str]:
    """Les 3 en-têtes OBO sortants, en minuscules (contrat portail figé).

    `now` injectable pour les tests ; en production c'est l'appelant qui ne
    passe rien, pour que `ts` soit l'instant du DISPATCH (pas celui de
    l'event) — un event rejoué longtemps après reste ainsi dans la fenêtre
    anti-rejeu de 300 s côté portail.
    """
    ts = int(now or time.time())
    return {
        "x-portal-actor": actor,
        "x-portal-actor-timestamp": str(ts),
        "x-portal-actor-signature": sign_actor(actor, ts, secret),
    }


def bearer_secret(headers: dict[str, str]) -> str | None:
    """Valeur du header `Authorization: Bearer <secret>`, casse insensible.

    `None` si l'en-tête est absent, ou présent sans préfixe `Bearer ` — un
    automate qui ne porte pas de jeton Bearer ne peut pas servir de clé HMAC
    pour le relais OBO (garde de configuration posée à l'écriture côté
    service ; ici on ne fait que la relire au dispatch).
    """
    for name, value in headers.items():
        if name.lower() == "authorization":
            if value.startswith(_BEARER_PREFIX):
                return value[len(_BEARER_PREFIX) :]
            return None
    return None
