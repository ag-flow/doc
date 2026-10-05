"""Garde-fous d'usage des templates (écran Templates, DoD).

Sauté quand `templates/` n'est pas monté (sandbox) — même contrainte que
test_template_import (voir LESSONS : monter le repo entier en conteneur).
"""

from __future__ import annotations

import asyncpg
import pytest

from docflow.templates.router import _TEMPLATES_DIR

pytestmark = pytest.mark.skipif(
    not _TEMPLATES_DIR.exists(), reason="templates/ absent (repo non monté en entier)"
)


async def test_delete_template_used_by_blocks_is_refused(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Un template dont les types portent des blocs ne se supprime pas ;
    le 409 liste les blocs concernés (workspace / label)."""
    import yaml
    from fastapi import HTTPException

    from docflow.templates.importer import run_import
    from docflow.templates.models import Template
    from docflow.templates.router import delete_template

    tpl_file = sorted(_TEMPLATES_DIR.glob("*.yaml"))[0]
    tpl = Template.model_validate(yaml.safe_load(tpl_file.read_text()))
    await run_import(db_pool, "test-ws", tpl, dry_run=False)

    wk = test_workspace["workspace_technical_key"]
    async with db_pool.acquire() as conn:
        type_id = await conn.fetchval(
            "SELECT id FROM functional_type "
            "WHERE workspace_technical_key = $1 AND source_template = $2 "
            "AND parent IS NULL LIMIT 1",
            wk,
            tpl.template,
        )
        assert type_id is not None
        await conn.execute(
            "INSERT INTO data_block (slug, label, functional_type_ref, "
            "workspace_technical_key) VALUES ('tpl-usage-blk', 'Bloc template', $1, $2)",
            type_id,
            wk,
        )

    class _Req:
        class app:
            class state:
                pool = None

    req = _Req()
    req.app.state.pool = db_pool  # type: ignore[attr-defined]
    with pytest.raises(HTTPException) as exc:
        await delete_template(tpl.template, req, None)  # type: ignore[arg-type]
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert "1 bloc(s)" in detail["message"]
    assert detail["blocks"] == ["test-ws / Bloc template"]
