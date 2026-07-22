"""Signature HMAC des requêtes d'ingestion (contrat producteur §3).

Le HMAC-SHA256 porte sur les **octets bruts** du corps posté — jamais sur une
re-sérialisation. La valeur est le hexdigest **brut** (64 caractères hex, SANS
préfixe `sha256=`), placé dans l'en-tête `x-signature`.
"""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_HEADER = "x-signature"


def sign_body(secret: str, body: bytes) -> str:
    """HMAC-SHA256 des octets `body` → hexdigest brut (64 car., sans préfixe)."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
