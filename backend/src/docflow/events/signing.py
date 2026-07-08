"""Signature HMAC des requêtes d'ingestion (contrat producteur §3).

Le HMAC-SHA256 porte sur les **octets bruts** du corps posté — jamais sur une
re-sérialisation. La valeur retournée est destinée à l'en-tête `X-Signature`,
préfixée `sha256=` (convention type X-Hub-Signature-256).
"""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_HEADER = "X-Signature"


def sign_body(secret: str, body: bytes) -> str:
    """HMAC-SHA256 des octets `body`, format `sha256=<hexdigest>`."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"
