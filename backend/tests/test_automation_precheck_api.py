"""La pré-condition doit traverser le service, pas seulement la base.

Le worker lit la colonne `precheck` ; encore faut-il qu'on puisse la REMPLIR
autrement qu'en SQL direct. Ajouter un champ à un automate oblige à toucher une
quinzaine d'énumérations de colonnes dans `service.py` — création, relectures,
mise à jour, duplication. C'est exactement là qu'un champ se perd : l'épic porte
déjà un ticket sur un `template_slug` oublié entre deux surfaces.

Ces tests existent pour que l'oubli se VOIE, à la création comme à la copie.
"""

from __future__ import annotations

import uuid

import asyncpg

from docflow.automations import service
from docflow.schemas.automations import (
    AutomationCreate,
    AutomationPrecheck,
    AutomationUpdate,
)

_SPEC = {
    "url": "https://rag.example/api/v1/workspaces/{event.workspaceSlug}-docs",
    "method": "GET",
    "rules": [{"status": [404], "then": "proceed"}],
    "default": "skip",
}


def _dump(spec: AutomationPrecheck | None) -> dict | None:
    """Compare ce qui a été STOCKÉ, pas la forme de l'objet rendu.

    Le service rend un modèle pydantic ; la spécification de référence est un
    dict. `exclude_none` écarte les critères non déclarés, qui ne doivent pas
    apparaître comme posés.
    """
    return None if spec is None else spec.model_dump(exclude_none=True)


async def _ws(pool: asyncpg.Pool) -> str:
    slug = f"pcapi-{uuid.uuid4().hex[:8]}"
    await pool.execute("INSERT INTO workspace (slug, label) VALUES ($1,$2)", slug, "PC API")
    return slug


def _body(label: str, slugs: list[str], precheck: dict | None) -> AutomationCreate:
    return AutomationCreate(
        label=label,
        event_codes=["docflow.block.created.v1"],
        url="https://rag.example/api/v1/workspaces",
        http_method="POST",
        workspace_slugs=slugs,
        precheck=precheck,
    )


async def test_la_precondition_survit_a_la_creation_et_a_la_relecture(
    db_pool: asyncpg.Pool,
) -> None:
    ws = await _ws(db_pool)

    created = await service.create_automation(db_pool, None, _body("Avec", [ws], _SPEC))
    assert _dump(created.precheck) == _SPEC, "perdue à la création"

    relu = await service.get_automation(db_pool, None, created.id)
    assert _dump(relu.precheck) == _SPEC, "perdue à la relecture"


async def test_un_automate_sans_precondition_la_rend_nulle(db_pool: asyncpg.Pool) -> None:
    """Le cas de tous les automates existants : rien ne change pour eux."""
    ws = await _ws(db_pool)

    created = await service.create_automation(db_pool, None, _body("Sans", [ws], None))

    assert created.precheck is None


async def test_la_precondition_se_modifie_et_se_retire(db_pool: asyncpg.Pool) -> None:
    ws = await _ws(db_pool)
    created = await service.create_automation(db_pool, None, _body("Modif", [ws], None))

    posee = await service.update_automation(
        db_pool, None, created.id, AutomationUpdate(precheck=_SPEC)
    )
    assert _dump(posee.precheck) == _SPEC, "perdue à la mise à jour"

    # Retirer la pré-condition doit être possible : un automate doit pouvoir
    # redevenir inconditionnel sans être recréé.
    retiree = await service.update_automation(
        db_pool, None, created.id, AutomationUpdate(precheck=None, label="Modif 2")
    )
    assert retiree.precheck is None


async def test_la_duplication_emporte_la_precondition(db_pool: asyncpg.Pool) -> None:
    """Dupliquer un automate sans sa pré-condition produirait une copie qui
    appelle là où l'original s'abstient — silencieusement plus agressive."""
    ws = await _ws(db_pool)
    created = await service.create_automation(db_pool, None, _body("Source", [ws], _SPEC))

    copie = await service.clone_automation(db_pool, None, created.id)

    assert _dump(copie.precheck) == _SPEC
