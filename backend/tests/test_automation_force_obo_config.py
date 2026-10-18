"""Toggle `force_obo` par automate — garde de configuration (chantier OBO sortant).

`force_obo=True` promet qu'un automate relaiera l'identité de l'acteur plutôt
que d'appeler avec ses propres credentials. La POSE effective de l'en-tête de
relais est une AUTRE tâche (worker) ; celle-ci ne porte que le signal et sa
garde : un automate qui force l'OBO sans porter de header `Authorization`
actif commençant par « Bearer » promettrait un relais qu'il ne peut pas tenir
— refusé en 422 (`obo_requires_bearer`), avant toute écriture en base.

Placé à plat (`tests/test_automation_*.py`), comme le reste des tests
d'automates : il n'existe pas de dossier `tests/automations/`.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.automations import service
from docflow.schemas.automations import AutomationCreate, AutomationHeaderIn, AutomationUpdate

_CREATED = "docflow.block.created.v1"


async def _ws(pool: asyncpg.Pool) -> str:
    slug = f"force-obo-{uuid.uuid4().hex[:8]}"
    await pool.execute("INSERT INTO workspace (slug, label) VALUES ($1, $2)", slug, "Force OBO")
    return slug


def _body(
    force_obo: bool,
    headers: list[AutomationHeaderIn] | None = None,
    slugs: list[str] | None = None,
) -> AutomationCreate:
    return AutomationCreate(
        label="OBO",
        event_codes=[_CREATED],
        url="https://rag.example/api",
        http_method="POST",
        workspace_slugs=slugs or [],
        force_obo=force_obo,
        headers=headers or [],
    )


async def test_force_obo_sans_bearer_est_refuse_en_422(db_pool: asyncpg.Pool) -> None:
    ws = await _ws(db_pool)

    with pytest.raises(HTTPException) as exc_info:
        await service.create_automation(db_pool, ws, _body(force_obo=True, slugs=[ws]))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "obo_requires_bearer"

    # Rien n'a été écrit : le refus a lieu AVANT toute insertion.
    count = await db_pool.fetchval(
        "SELECT count(*) FROM automation WHERE workspace_technical_key = "
        "(SELECT workspace_technical_key FROM workspace WHERE slug = $1)",
        ws,
    )
    assert count == 0


async def test_force_obo_avec_bearer_actif_est_accepte_et_relu(db_pool: asyncpg.Pool) -> None:
    ws = await _ws(db_pool)
    headers = [AutomationHeaderIn(name="Authorization", value_prefix="Bearer ")]

    created = await service.create_automation(
        db_pool, ws, _body(force_obo=True, headers=headers, slugs=[ws])
    )

    assert created.force_obo is True

    relu = await service.get_automation(db_pool, ws, created.id)
    assert relu.force_obo is True


async def test_force_obo_avec_bearer_desactive_est_refuse(db_pool: asyncpg.Pool) -> None:
    """Un header désactivé ne compte pas comme porteur — il ne partira pas."""
    ws = await _ws(db_pool)
    headers = [
        AutomationHeaderIn(name="Authorization", value_prefix="Bearer ", enabled=False),
    ]

    with pytest.raises(HTTPException) as exc_info:
        await service.create_automation(
            db_pool, ws, _body(force_obo=True, headers=headers, slugs=[ws])
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "obo_requires_bearer"


async def test_force_obo_false_sans_header_est_accepte(db_pool: asyncpg.Pool) -> None:
    """Défaut inchangé : un automate sans force_obo n'a jamais besoin de Bearer."""
    ws = await _ws(db_pool)

    created = await service.create_automation(db_pool, ws, _body(force_obo=False, slugs=[ws]))

    assert created.force_obo is False


async def test_update_vers_force_obo_sans_bearer_existant_est_refuse(
    db_pool: asyncpg.Pool,
) -> None:
    """Le garde-fou vaut aussi à la mise à jour : basculer force_obo=True sur un
    automate qui n'a jamais eu de header Bearer doit être refusé, pas accepté
    silencieusement parce que seul `force_obo` a changé dans le corps."""
    ws = await _ws(db_pool)
    created = await service.create_automation(db_pool, ws, _body(force_obo=False, slugs=[ws]))

    with pytest.raises(HTTPException) as exc_info:
        await service.update_automation(db_pool, ws, created.id, AutomationUpdate(force_obo=True))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "obo_requires_bearer"


async def test_update_vers_force_obo_avec_bearer_pose_dans_le_meme_appel(
    db_pool: asyncpg.Pool,
) -> None:
    """Poser force_obo=True ET le header Bearer dans le même PATCH doit passer :
    la garde doit lire les headers DU corps, pas seulement ceux déjà en base."""
    ws = await _ws(db_pool)
    created = await service.create_automation(db_pool, ws, _body(force_obo=False, slugs=[ws]))

    updated = await service.update_automation(
        db_pool,
        ws,
        created.id,
        AutomationUpdate(
            force_obo=True,
            headers=[AutomationHeaderIn(name="Authorization", value_prefix="Bearer ")],
        ),
    )

    assert updated.force_obo is True
