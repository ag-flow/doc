from __future__ import annotations

import json

from cryptography.fernet import Fernet


def encrypt_headers(key: str, headers: dict[str, str]) -> bytes:
    """Chiffre le blob JSON des headers avec Fernet. Clé = base64-urlsafe 32 octets."""
    f = Fernet(key.encode())
    return f.encrypt(json.dumps(headers).encode())


def decrypt_headers(key: str, data: bytes) -> dict[str, str]:
    """Déchiffre et désérialise un blob produit par encrypt_headers."""
    f = Fernet(key.encode())
    return json.loads(f.decrypt(data).decode())  # type: ignore[no-any-return]
