"""Préférences d'interface de l'utilisateur connecté.

Key/value JSONB rattaché au compte : un choix d'interface (colonnes affichées,
repli d'un panneau…) suit l'utilisateur d'un poste à l'autre. Ce n'est PAS un
stockage applicatif : la valeur est bornée et opaque pour le serveur.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from docflow.auth.deps import require_authenticated
from docflow.schemas.auth import AuthUser

router = APIRouter(tags=["me"])
_Auth = Depends(require_authenticated)

# Clé namespacée : `doc-columns:mon-ws:mon-bloc`. Stricte pour rester lisible
# dans la table et interdire tout caractère de contrôle.
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,199}$")
# Une préférence d'UI tient largement là-dedans ; au-delà c'est un détournement.
_MAX_VALUE_BYTES = 16_384


class PreferenceOut(BaseModel):
    key: str
    # null = jamais enregistrée (distinct d'une valeur JSON `null`, refusée).
    value: Any | None


class PreferenceIn(BaseModel):
    model_config = {"extra": "forbid"}

    value: Any


def _check_key(key: str) -> str:
    if not _KEY_RE.match(key):
        raise HTTPException(422, "clé de préférence invalide")
    return key


@router.get("/me/preferences/{key}", response_model=PreferenceOut)
async def get_preference(key: str, request: Request, user: AuthUser = _Auth) -> PreferenceOut:
    _check_key(key)
    raw = await request.app.state.pool.fetchval(
        "SELECT value FROM user_preference WHERE user_id = $1 AND pref_key = $2",
        user.id,
        key,
    )
    return PreferenceOut(key=key, value=json.loads(raw) if raw is not None else None)


@router.put("/me/preferences/{key}", response_model=PreferenceOut)
async def put_preference(
    key: str, body: PreferenceIn, request: Request, user: AuthUser = _Auth
) -> PreferenceOut:
    _check_key(key)
    if body.value is None:
        # Effacer = revenir au défaut : la ligne disparaît.
        await request.app.state.pool.execute(
            "DELETE FROM user_preference WHERE user_id = $1 AND pref_key = $2",
            user.id,
            key,
        )
        return PreferenceOut(key=key, value=None)

    encoded = json.dumps(body.value, ensure_ascii=False)
    if len(encoded.encode()) > _MAX_VALUE_BYTES:
        raise HTTPException(422, "valeur de préférence trop volumineuse")
    await request.app.state.pool.execute(
        "INSERT INTO user_preference (user_id, pref_key, value) VALUES ($1, $2, $3) "
        "ON CONFLICT (user_id, pref_key) "
        "DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
        user.id,
        key,
        encoded,
    )
    return PreferenceOut(key=key, value=body.value)
