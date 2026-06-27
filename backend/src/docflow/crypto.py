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


def encrypt_str(key: str, value: str) -> str:
    """Chiffre une chaîne avec Fernet, retourne base64 URL-safe."""
    return Fernet(key.encode()).encrypt(value.encode()).decode()


def decrypt_str(key: str, data: str) -> str:
    """Déchiffre une chaîne produite par encrypt_str."""
    return Fernet(key.encode()).decrypt(data.encode()).decode()
