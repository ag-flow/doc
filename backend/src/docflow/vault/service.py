"""Façade du sous-système vault/secrets.

L'implémentation vit dans des sous-modules dédiés (limite des 300 lignes) ; ce
module ré-exporte l'API publique pour préserver les appels `service.X` (routeurs,
résolveur, tests) et les points de patch existants (`docflow.vault.service.*`).
"""

from __future__ import annotations

from docflow.vault.endpoints import (
    check_wallet,
    create_wallet,
    delete_wallet,
    get_api_key,
    list_wallets,
)
from docflow.vault.hmac_secrets import (
    create_hmac_secret,
    list_hmac_secrets,
    resolve_hmac_value,
    reveal_hmac_secret,
)
from docflow.vault.refs import assert_refs_owned, assert_refs_resolvable
from docflow.vault.user_secrets import (
    create_secret,
    delete_secret,
    list_secrets,
    resolve_user_secret_value,
)

__all__ = [
    "assert_refs_owned",
    "assert_refs_resolvable",
    "check_wallet",
    "create_hmac_secret",
    "create_secret",
    "create_wallet",
    "delete_secret",
    "delete_wallet",
    "get_api_key",
    "list_hmac_secrets",
    "list_secrets",
    "list_wallets",
    "resolve_hmac_value",
    "resolve_user_secret_value",
    "reveal_hmac_secret",
]
