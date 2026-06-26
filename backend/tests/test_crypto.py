from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from docflow.crypto import decrypt_headers, encrypt_headers


def _fresh_key() -> str:
    return Fernet.generate_key().decode()


def test_encrypt_decrypt_roundtrip() -> None:
    key = _fresh_key()
    headers = {"Authorization": "Bearer secret", "X-Custom": "value"}
    blob = encrypt_headers(key, headers)
    assert isinstance(blob, bytes)
    assert blob != json.dumps(headers).encode()  # pas en clair
    recovered = decrypt_headers(key, blob)
    assert recovered == headers


def test_encrypted_blob_differs_from_plaintext() -> None:
    key = _fresh_key()
    h = {"X-Secret": "topsecret"}
    blob = encrypt_headers(key, h)
    assert b"topsecret" not in blob


def test_wrong_key_raises() -> None:
    key1, key2 = _fresh_key(), _fresh_key()
    blob = encrypt_headers(key1, {"a": "b"})
    with pytest.raises(Exception):
        decrypt_headers(key2, blob)
