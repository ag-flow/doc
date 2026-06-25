from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from docflow.blocks import service as block_svc
from docflow.schemas.block import DataBlockCreate, DataBlockUpdate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _make_types(pool: asyncpg.Pool) -> None:
    """Crée la hiérarchie : epic (racine) → feature (fils de epic)."""
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await type_svc.create_type(
        pool, _WS, FunctionalTypeCreate(slug="feature", label="Feature", parent_slug="epic")
    )


async def test_create_block_root(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_types(db_pool)
    block = await block_svc.create_block(
        db_pool, _WS, DataBlockCreate(slug="my-epic", label="My Epic", functional_type_slug="epic")
    )
    assert block.slug == "my-epic"
    assert block.parent_slug is None


async def test_create_block_child(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_types(db_pool)
    await block_svc.create_block(
        db_pool, _WS, DataBlockCreate(slug="epic-1", label="Epic 1", functional_type_slug="epic")
    )
    child = await block_svc.create_block(
        db_pool, _WS,
        DataBlockCreate(slug="feat-1", label="Feat 1", functional_type_slug="feature",
                        parent_slug="epic-1"),
    )
    assert child.parent_slug == "epic-1"


async def test_mirror_constraint_i5_root_type(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """I-5 : un bloc racine doit avoir un type racine."""
    await _make_types(db_pool)
    with pytest.raises(HTTPException) as exc:
        await block_svc.create_block(
            db_pool, _WS,
            DataBlockCreate(slug="bad", label="Bad", functional_type_slug="feature"),
        )
    assert exc.value.status_code == 422
    assert "I-5" in exc.value.detail


async def test_mirror_constraint_i5_wrong_parent_type(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """I-5 : type enfant doit être fils direct du type du parent."""
    await _make_types(db_pool)
    # Créer un autre type racine
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="task", label="Task")
    )
    await block_svc.create_block(
        db_pool, _WS, DataBlockCreate(slug="epic-1", label="Epic 1", functional_type_slug="epic")
    )
    with pytest.raises(HTTPException) as exc:
        # task n'est pas fils de epic → rejet
        await block_svc.create_block(
            db_pool, _WS,
            DataBlockCreate(slug="task-1", label="Task 1", functional_type_slug="task",
                            parent_slug="epic-1"),
        )
    assert exc.value.status_code == 422
    assert "I-5" in exc.value.detail


async def test_block_slug_unique_per_workspace(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _make_types(db_pool)
    await block_svc.create_block(
        db_pool, _WS, DataBlockCreate(slug="dup-block", label="A", functional_type_slug="epic")
    )
    with pytest.raises(HTTPException) as exc:
        await block_svc.create_block(
            db_pool, _WS,
            DataBlockCreate(slug="dup-block", label="B", functional_type_slug="epic"),
        )
    assert exc.value.status_code == 409


async def test_list_blocks(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_types(db_pool)
    await block_svc.create_block(
        db_pool, _WS, DataBlockCreate(slug="e1", label="E1", functional_type_slug="epic")
    )
    await block_svc.create_block(
        db_pool, _WS, DataBlockCreate(slug="e2", label="E2", functional_type_slug="epic")
    )
    blocks = await block_svc.list_blocks(db_pool, _WS)
    slugs = [b.slug for b in blocks]
    assert "e1" in slugs and "e2" in slugs


async def test_update_block_label(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_types(db_pool)
    await block_svc.create_block(
        db_pool, _WS, DataBlockCreate(slug="epic-u", label="Old", functional_type_slug="epic")
    )
    updated = await block_svc.update_block(
        db_pool, _WS, "epic-u", DataBlockUpdate(label="New Label")
    )
    assert updated.label == "New Label"


async def test_delete_block_with_children_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _make_types(db_pool)
    await block_svc.create_block(
        db_pool, _WS, DataBlockCreate(slug="e-root", label="Root", functional_type_slug="epic")
    )
    await block_svc.create_block(
        db_pool, _WS,
        DataBlockCreate(slug="f-child", label="Child", functional_type_slug="feature",
                        parent_slug="e-root"),
    )
    with pytest.raises(HTTPException) as exc:
        await block_svc.delete_block(db_pool, _WS, "e-root")
    assert exc.value.status_code == 409


async def test_block_slug_invalid() -> None:
    with pytest.raises(ValidationError):
        DataBlockCreate(slug="UPPER", label="Bad", functional_type_slug="epic")
