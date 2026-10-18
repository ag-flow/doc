"""Signeur OBO sortant (Task 4) — primitives pures, sans DB ni réseau.

Miroir volontaire de `rag.auth.obo.sign_actor` : on réimplémente le HMAC de
référence ICI, localement, plutôt que d'importer `rag` (couplage interdit,
CLAUDE.md). Si le contrat amont change un jour, c'est cette réimplémentation
qui doit être mise à jour à la main.

Placé à plat (`tests/test_obo_*.py`), comme le reste des tests d'automates :
il n'existe pas de dossier `tests/automations/`.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from docflow.automations.obo_sign import bearer_secret, obo_headers, sign_actor


def _reference_hmac(actor: str, timestamp: int, secret: str) -> str:
    payload = f"{actor}\n{timestamp}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_sign_actor_est_le_hmac_sha256_hex_de_acteur_newline_timestamp() -> None:
    assert sign_actor("g", 1700000000, "k") == _reference_hmac("g", 1700000000, "k")


def test_sign_actor_change_si_le_secret_change() -> None:
    """Discriminant : deux clés différentes ne doivent jamais produire la même
    signature pour la même charge — sinon le test ne prouverait rien."""
    assert sign_actor("g", 1700000000, "k1") != sign_actor("g", 1700000000, "k2")


def test_obo_headers_pose_les_3_cles_en_minuscules_avec_signature_coherente() -> None:
    headers = obo_headers("g", "k", now=1700000000)

    assert set(headers) == {
        "x-portal-actor",
        "x-portal-actor-timestamp",
        "x-portal-actor-signature",
    }
    assert headers["x-portal-actor"] == "g"
    assert headers["x-portal-actor-timestamp"] == "1700000000"
    assert headers["x-portal-actor-signature"] == _reference_hmac("g", 1700000000, "k")


def test_obo_headers_sans_now_utilise_l_instant_d_appel() -> None:
    before = time.time()
    headers = obo_headers("g", "k")
    after = time.time()

    ts = int(headers["x-portal-actor-timestamp"])
    assert int(before) <= ts <= int(after) + 1


def test_bearer_secret_lit_authorization_casse_standard() -> None:
    assert bearer_secret({"Authorization": "Bearer abc"}) == "abc"


def test_bearer_secret_lit_authorization_casse_minuscule() -> None:
    assert bearer_secret({"authorization": "Bearer abc"}) == "abc"


def test_bearer_secret_absent_renvoie_none() -> None:
    assert bearer_secret({}) is None


def test_bearer_secret_non_bearer_renvoie_none() -> None:
    assert bearer_secret({"Authorization": "Basic abc"}) is None
