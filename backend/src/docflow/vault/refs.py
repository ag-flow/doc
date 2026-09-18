"""Validation des références de secrets au point d'écriture (config).

- `assert_refs_owned` : isolation par propriétaire des `${secret://}`/`${hmac://}`.
- `assert_refs_resolvable` : résolubilité à la configuration (endpoint existant).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable

import asyncpg
from fastapi import HTTPException

# Référence à un secret utilisateur par id : ${secret://uuid} ou ${hmac://uuid}.
# Seuls ces deux schémas désignent un `user_secret` (propriété par utilisateur) ;
# ${vault://…} désigne un coffre d'instance (superadmin), hors isolation par user.
_OWNED_REF_RE = re.compile(r"^\$\{(?:secret|hmac)://([0-9a-fA-F-]{36})\}$")

_VAULT_REF_RE = re.compile(r"^\$\{vault://([^/:]+):(/.+)\}$")
_SECRET_REF_RE = re.compile(r"^\$\{secret://([0-9a-fA-F-]{36})\}$")


async def assert_refs_owned(
    pool: asyncpg.Pool,
    refs: Iterable[str | None],
    owner_id: uuid.UUID,
) -> None:
    """Vérifie que toute référence ${secret://}/${hmac://} appartient à `owner_id`.

    Isolation stricte par propriétaire (STANDARD « Gestion des secrets » §1/§6) :
    on ne peut pas rattacher à un automate / webhook / config le secret d'un
    AUTRE utilisateur. Point d'application = l'écriture (là où l'identité existe),
    puisque la résolution ultérieure se fait côté worker, sans contexte requête.
    Les ${vault://…} (coffres d'instance) ne sont pas concernés. 403 si une
    référence pointe un secret inexistant ou d'un autre propriétaire.
    """
    seen: set[uuid.UUID] = set()
    for ref in refs:
        if not ref:
            continue
        m = _OWNED_REF_RE.match(ref.strip())
        if m:
            seen.add(uuid.UUID(m.group(1)))
    if not seen:
        return
    async with pool.acquire() as conn:
        owned = {
            r["id"]
            for r in await conn.fetch(
                "SELECT id FROM user_secret WHERE id = ANY($1::uuid[]) AND owner_ref = $2",
                list(seen),
                owner_id,
            )
        }
    foreign = seen - owned
    if foreign:
        raise HTTPException(
            status_code=403,
            detail=f"secret(s) non accessible(s) (autre propriétaire ou inexistant) : "
            f"{', '.join(str(s) for s in sorted(foreign))}",
        )


async def assert_refs_resolvable(pool: asyncpg.Pool, refs: Iterable[str | None]) -> None:
    """Validation de résolubilité à la CONFIGURATION (STANDARD Harpocrate §6).

    Rattacher une référence à un consommateur vérifie qu'elle est résoluble :
    l'endpoint désigné existe (donc sa clé d'API est présente, `api_key_secret_ref`
    étant NOT NULL). Vérification structurelle (aucun appel réseau) ; 422 sinon —
    une erreur de configuration ne doit pas se découvrir à la première utilisation.
    """
    async with pool.acquire() as conn:
        for ref in refs:
            if not ref:
                continue
            r = ref.strip()
            mv = _VAULT_REF_RE.match(r)
            if mv:
                identifier = mv.group(1)
                ok = await conn.fetchval("SELECT 1 FROM vault_wallet WHERE name = $1", identifier)
                if not ok:
                    raise HTTPException(
                        422,
                        f"Référence non résoluble : endpoint vault « {identifier} » inexistant.",
                    )
                continue
            ms = _SECRET_REF_RE.match(r)
            if ms:
                row = await conn.fetchrow(
                    "SELECT storage_type, vault_identifier FROM user_secret WHERE id = $1",
                    uuid.UUID(ms.group(1)),
                )
                if row and row["storage_type"] == "vault":
                    ok = await conn.fetchval(
                        "SELECT 1 FROM vault_wallet WHERE name = $1", row["vault_identifier"]
                    )
                    if not ok:
                        raise HTTPException(
                            422,
                            "Référence non résoluble : le secret vault pointe l'endpoint "
                            f"« {row['vault_identifier']} » inexistant.",
                        )
