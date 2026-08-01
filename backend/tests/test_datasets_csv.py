"""Tests Feature 3 — import / export CSV des datasets tabulaires.

Import avec/sans en-tête, inférence de type par scan de colonne, lignes fautives
reportées sans faire échouer l'import, mode append (mapping par slug), round-trip
import → export → import, slugify des en-têtes, et garde d'accès via ``_call_tool``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest

from docflow.datasets import service
from docflow.datasets.csv_io import export_csv, import_csv
from docflow.mcp.server import _call_tool, configure
from docflow.mcp.session import McpSession, reset_current_session, set_current_session
from docflow.schemas.auth import AuthUser


def _json(result: list) -> dict:
    return json.loads((result.content if hasattr(result, "content") else result)[0].text)


def _admin_user(uid: uuid.UUID) -> AuthUser:
    return AuthUser(
        id=uid,
        email="csv-admin@test.local",
        label="CSV Admin",
        is_admin=True,
        validated=True,
        disabled=False,
    )


@pytest.fixture()
async def ws(db_pool: asyncpg.Pool) -> AsyncIterator[dict[str, object]]:
    configure(db_pool)
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "csv-ws")
    wk = await db_pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) RETURNING workspace_technical_key",
        "csv-ws",
        "CSV WS",
    )
    uid = await db_pool.fetchval(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, true) "
        "ON CONFLICT (email) DO UPDATE SET label = EXCLUDED.label RETURNING id",
        "csv-admin@test.local",
        "CSV Admin",
    )
    token = set_current_session(McpSession(user=_admin_user(uid)))
    try:
        yield {"wk": wk, "ws_slug": "csv-ws", "uid": uid}
    finally:
        reset_current_session(token)
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "csv-ws")
        await db_pool.execute("DELETE FROM app_user WHERE email = 'csv-admin@test.local'")


def _cols_by_slug(ds: dict) -> dict[str, dict]:
    return {c["slug"]: c for c in ds["columns"]}


# ---------------------------------------------------------------------------
# Import avec en-tête + inférence de type
# ---------------------------------------------------------------------------


async def test_import_with_header(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    result = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="produits",
        label="Produits",
        csv_text="nom,prix,actif\nStylo,1.5,true\nGomme,2,false",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    assert result["columns_created"] == 3
    assert result["rows_created"] == 2
    assert result["rows_skipped"] == 0
    assert result["errors"] == []

    ds = await service.get_dataset(db_pool, ws_slug, uuid.UUID(str(result["dataset_id"])))
    cols = _cols_by_slug(ds)
    assert cols["nom"]["type"] == "text"
    assert cols["prix"]["type"] == "float"
    assert cols["actif"]["type"] == "bool"
    assert len(ds["rows"]) == 2
    assert ds["rows"][0]["cells"] == {"nom": "Stylo", "prix": "1.5", "actif": "true"}


async def test_type_inference(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    result = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="infer",
        label="Infer",
        csv_text=(
            "entier,decimal,jour,texte\n"
            "1,1,2026-01-01,abc\n"
            "2,2.5,2026-02-15,def\n"
            "3,4,2026-03-30,42x"
        ),
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    ds = await service.get_dataset(db_pool, ws_slug, uuid.UUID(str(result["dataset_id"])))
    cols = _cols_by_slug(ds)
    assert cols["entier"]["type"] == "int"
    assert cols["decimal"]["type"] == "float"
    assert cols["jour"]["type"] == "date"
    assert cols["texte"]["type"] == "text"


# ---------------------------------------------------------------------------
# Lignes fautives : reportées dans errors, les autres importées
# ---------------------------------------------------------------------------


async def test_faulty_arity_reported(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    result = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="fautes",
        label="Fautes",
        # ligne "Trop,3,extra" = 3 cellules pour 2 colonnes → arité KO, reportée
        csv_text="nom,prix\nStylo,1.5\nTrop,3,extra\nRegle,2",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    assert result["rows_created"] == 2
    assert result["rows_skipped"] == 1
    assert len(result["errors"]) == 1
    assert "arité" in result["errors"][0]["reason"]

    ds = await service.get_dataset(db_pool, ws_slug, uuid.UUID(str(result["dataset_id"])))
    names = {r["cells"].get("nom") for r in ds["rows"]}
    assert names == {"Stylo", "Regle"}


async def test_faulty_coercion_reported_on_append(
    db_pool: asyncpg.Pool, ws: dict[str, object]
) -> None:
    ws_slug = str(ws["ws_slug"])
    # colonne prix inférée float à la création
    first = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="fautes2",
        label="Fautes2",
        csv_text="nom,prix\nStylo,1.5",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    ds_id = uuid.UUID(str(first["dataset_id"]))
    # append : "cher" n'est pas convertible dans la colonne float existante → error
    result = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=ds_id,
        slug=None,
        label=None,
        csv_text="nom,prix\nGomme,cher\nRegle,2",
        mode="append",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    assert result["rows_created"] == 1
    assert result["rows_skipped"] == 1
    assert len(result["errors"]) == 1
    assert "float" in result["errors"][0]["reason"] or "cher" in result["errors"][0]["reason"]


# ---------------------------------------------------------------------------
# Mode append : mapping par slug d'en-tête, colonnes inchangées
# ---------------------------------------------------------------------------


async def test_append_mode(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    first = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="app",
        label="App",
        csv_text="nom,prix\nStylo,1.5",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    ds_id = uuid.UUID(str(first["dataset_id"]))

    result = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=ds_id,
        slug=None,
        label=None,
        csv_text="nom,prix\nGomme,2\nRegle,3.5",
        mode="append",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    assert result["columns_created"] == 0
    assert result["rows_created"] == 2

    ds = await service.get_dataset(db_pool, ws_slug, ds_id)
    assert [c["slug"] for c in ds["columns"]] == ["nom", "prix"]
    assert len(ds["rows"]) == 3
    assert _cols_by_slug(ds)["prix"]["type"] == "float"  # type inchangé (append)


async def test_append_unknown_header_creates_text_column(
    db_pool: asyncpg.Pool, ws: dict[str, object]
) -> None:
    ws_slug = str(ws["ws_slug"])
    first = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="app2",
        label="App2",
        csv_text="nom\nStylo",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    ds_id = uuid.UUID(str(first["dataset_id"]))
    result = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=ds_id,
        slug=None,
        label=None,
        csv_text="nom,couleur\nGomme,rouge",
        mode="append",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    assert result["columns_created"] == 1
    ds = await service.get_dataset(db_pool, ws_slug, ds_id)
    assert _cols_by_slug(ds)["couleur"]["type"] == "text"


# ---------------------------------------------------------------------------
# Round-trip : import → export → import → même structure/valeurs
# ---------------------------------------------------------------------------


async def test_round_trip(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    src = "nom,prix,actif\nStylo,1.5,true\nGomme,2,false"
    first = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="rt1",
        label="RT1",
        csv_text=src,
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    ds1 = await service.get_dataset(db_pool, ws_slug, uuid.UUID(str(first["dataset_id"])))

    exported = await export_csv(
        db_pool, ws_slug, uuid.UUID(str(first["dataset_id"])), header="slug"
    )
    assert exported.splitlines()[0] == "nom,prix,actif"

    second = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="rt2",
        label="RT2",
        csv_text=exported,
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    ds2 = await service.get_dataset(db_pool, ws_slug, uuid.UUID(str(second["dataset_id"])))

    assert [(c["slug"], c["type"]) for c in ds1["columns"]] == [
        (c["slug"], c["type"]) for c in ds2["columns"]
    ]
    assert [r["cells"] for r in ds1["rows"]] == [r["cells"] for r in ds2["rows"]]


async def test_export_header_label(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    first = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="lbl",
        label="Lbl",
        csv_text="Nom Complet,Age\nAlice,30",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    exported = await export_csv(
        db_pool, ws_slug, uuid.UUID(str(first["dataset_id"])), header="label"
    )
    assert exported.splitlines()[0] == "Nom Complet,Age"


# ---------------------------------------------------------------------------
# Slugify des en-têtes
# ---------------------------------------------------------------------------


async def test_slugify_headers(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    result = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="slg",
        label="Slg",
        csv_text="Prix (€),Prix (€)\n1,2",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    ds = await service.get_dataset(db_pool, ws_slug, uuid.UUID(str(result["dataset_id"])))
    slugs = [c["slug"] for c in ds["columns"]]
    assert slugs[0] == "prix"
    assert slugs[1] == "prix-2"  # dédoublonnage
    assert ds["columns"][0]["label"] == "Prix (€)"


# ---------------------------------------------------------------------------
# Sans en-tête : colonnes col-1..col-n
# ---------------------------------------------------------------------------


async def test_import_without_header(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    result = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="noh",
        label="NoH",
        csv_text="1,alpha\n2,beta",
        has_header=False,
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    ds = await service.get_dataset(db_pool, ws_slug, uuid.UUID(str(result["dataset_id"])))
    cols = _cols_by_slug(ds)
    assert set(cols) == {"col-1", "col-2"}
    assert cols["col-1"]["type"] == "int"
    assert cols["col-2"]["type"] == "text"
    assert len(ds["rows"]) == 2


# ---------------------------------------------------------------------------
# replace : vide les colonnes/lignes existantes
# ---------------------------------------------------------------------------


async def test_replace_clears_existing(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    first = await import_csv(
        db_pool,
        ws_slug,
        dataset_id=None,
        slug="rep",
        label="Rep",
        csv_text="a,b\n1,2",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    ds_id = uuid.UUID(str(first["dataset_id"]))
    await import_csv(
        db_pool,
        ws_slug,
        dataset_id=ds_id,
        slug=None,
        label=None,
        csv_text="x,y,z\n7,8,9",
        mode="replace",
        created_by=ws["uid"],  # type: ignore[arg-type]
    )
    ds = await service.get_dataset(db_pool, ws_slug, ds_id)
    assert {c["slug"] for c in ds["columns"]} == {"x", "y", "z"}
    assert len(ds["rows"]) == 1


# ---------------------------------------------------------------------------
# Erreurs : dataset inconnu, création sans slug/label
# ---------------------------------------------------------------------------


async def test_import_unknown_dataset(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await import_csv(
            db_pool,
            str(ws["ws_slug"]),
            dataset_id=uuid.uuid4(),
            slug=None,
            label=None,
            csv_text="a\n1",
            created_by=ws["uid"],  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 404


async def test_import_create_requires_slug_label(
    db_pool: asyncpg.Pool, ws: dict[str, object]
) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await import_csv(
            db_pool,
            str(ws["ws_slug"]),
            dataset_id=None,
            slug=None,
            label=None,
            csv_text="a\n1",
            created_by=ws["uid"],  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# Tools MCP via _call_tool
# ---------------------------------------------------------------------------


async def test_import_export_via_tools(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    res = _json(
        await _call_tool(
            "import_dataset_csv",
            {
                "workspace_slug": ws_slug,
                "slug": "viatool",
                "label": "Via Tool",
                "csv": "nom,prix\nStylo,1.5\nGomme,2",
            },
        )
    )
    assert res["rows_created"] == 2
    ds_id = res["dataset_id"]

    exported = _json(
        await _call_tool(
            "export_dataset_csv",
            {"workspace_slug": ws_slug, "dataset_id": ds_id},
        )
    )
    assert "csv" in exported
    assert exported["csv"].splitlines()[0] == "nom,prix"


async def test_tool_access_denied_for_non_member(
    db_pool: asyncpg.Pool, ws: dict[str, object]
) -> None:
    ws_slug = str(ws["ws_slug"])
    outsider_id = await db_pool.fetchval(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, true) "
        "ON CONFLICT (email) DO UPDATE SET label = EXCLUDED.label RETURNING id",
        "csv-outsider@test.local",
        "Outsider",
    )
    outsider = AuthUser(
        id=outsider_id,
        email="csv-outsider@test.local",
        label="Outsider",
        is_admin=False,
        validated=True,
        disabled=False,
    )
    token = set_current_session(McpSession(user=outsider))
    try:
        res = _json(
            await _call_tool(
                "import_dataset_csv",
                {
                    "workspace_slug": ws_slug,
                    "slug": "denied",
                    "label": "Denied",
                    "csv": "a\n1",
                },
            )
        )
        assert "error" in res and "accès refusé" in res["error"]
    finally:
        reset_current_session(token)
        await db_pool.execute("DELETE FROM app_user WHERE email = 'csv-outsider@test.local'")
