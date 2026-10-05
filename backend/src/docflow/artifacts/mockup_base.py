"""Base CSS des maquettes (« mockup-base ») — identité, embarquement, propagation.

Une **base** est un artefact MUTABLE `text/css` : son `id` est le `base_id`, sa
`revision` est la **version**. Chaque maquette (artefact HTML mutable) embarque
le CSS de la base VERBATIM entre marqueurs stables :

    <style data-mockup-base="<base_id>" data-mockup-base-rev="<N>">
    …contenu de la base, copié tel quel…
    </style>

Le fichier reste auto-portant (s'ouvre seul, se télécharge tel quel). L'`id` dans
le marqueur permet de retrouver les maquettes d'une base ; la `rev` détecte la
dérive et sert d'ancre UNIQUE pour `patch_artifact` lors de la propagation.

Décision (cf. ticket) : la base n'est jamais injectée au rendu — la CSP du
serveur de preview l'interdit et le fichier cesserait d'être auto-portant. On
duplique donc quelques Ko dans chaque maquette, réparables par propagation.
"""

from __future__ import annotations

import re
import uuid

import asyncpg
from fastapi import HTTPException

from docflow.artifacts import mutable as mut
from docflow.artifacts import service as art_svc
from docflow.db.helpers import require_workspace

_MAQUETTE_MEDIA = "text/html"
_BASE_MEDIA = "text/css"


# ── Marqueurs ─────────────────────────────────────────────────────────────────


def build_block(base_id: uuid.UUID, revision: int, css: str) -> str:
    """Bloc `<style>` embarqué, format canonique (id + révision)."""
    return (
        f'<style data-mockup-base="{base_id}" data-mockup-base-rev="{revision}">\n{css}\n</style>'
    )


def _block_re(base_id: uuid.UUID) -> re.Pattern[str]:
    # Format émis par build_block uniquement (on maîtrise l'écriture) : id puis
    # rev. `.*?` + DOTALL : capture le contenu jusqu'au premier </style>.
    return re.compile(
        r'<style data-mockup-base="'
        + re.escape(str(base_id))
        + r'" data-mockup-base-rev="(\d+)">.*?</style>',
        re.DOTALL,
    )


def find_block(text: str, base_id: uuid.UUID) -> tuple[str, int] | None:
    """(bloc exact, révision embarquée) pour cette base, ou None si absente.

    Lève 422 si plusieurs blocs de la même base coexistent (fichier corrompu :
    l'ancre de patch ne serait plus unique)."""
    matches = list(_block_re(base_id).finditer(text))
    if not matches:
        return None
    if len(matches) > 1:
        raise HTTPException(
            status_code=422,
            detail=f"maquette corrompue : {len(matches)} blocs mockup-base pour {base_id}",
        )
    m = matches[0]
    return m.group(0), int(m.group(1))


def _insert_block(html: str, block: str) -> str:
    """Insère un bloc de base dans une maquette qui n'en a pas encore.

    Priorité : juste avant `</head>` (place naturelle d'une feuille de style),
    sinon avant `</body>`, sinon en tête. Insensible à la casse de la balise.
    """
    for tag in ("</head>", "</body>"):
        m = re.search(re.escape(tag), html, re.IGNORECASE)
        if m:
            return html[: m.start()] + block + "\n" + html[m.start() :]
    return block + "\n" + html


# ── Lecture de la base ────────────────────────────────────────────────────────


async def _base_head(conn: asyncpg.Connection, wk: uuid.UUID, base_id: uuid.UUID) -> asyncpg.Record:
    row = await conn.fetchrow(
        "SELECT id, revision, media_type, mutable, data FROM artifact "
        "WHERE id = $1 AND workspace_technical_key = $2",
        base_id,
        wk,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"base mockup {base_id} introuvable")
    if not row["mutable"] or row["media_type"] != _BASE_MEDIA:
        raise HTTPException(
            status_code=422, detail="l'artefact ciblé n'est pas une base mockup CSS"
        )
    return row


async def get_mockup_base(
    pool: asyncpg.Pool, ws_slug: str, base_id: uuid.UUID
) -> dict[str, object]:
    """Contenu CSS courant + révision de la base."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await _base_head(conn, wk, base_id)
    return {
        "base_id": base_id,
        "revision": row["revision"],
        "css": bytes(row["data"]).decode("utf-8"),
    }


# ── Écriture de la base ───────────────────────────────────────────────────────


async def set_mockup_base(
    pool: asyncpg.Pool,
    ws_slug: str,
    *,
    css: str,
    updated_by: uuid.UUID | None,
    max_bytes: int,
    base_id: uuid.UUID | None = None,
    if_revision: int | None = None,
    filename: str = "mockup-base.css",
) -> dict[str, object]:
    """Crée (base_id absent) ou met à jour (base_id + if_revision) la base CSS.

    La mise à jour ne PROPAGE rien : elle incrémente seulement la version de la
    base. La propagation vers les maquettes est un geste explicite séparé
    (`propagate_mockup_base`) — on ne réécrit jamais des dizaines de fichiers en
    effet de bord d'une écriture de base.
    """
    css = css.strip()
    if not css:
        raise HTTPException(status_code=422, detail="contenu CSS vide")
    if base_id is None:
        created = await art_svc.create_artifact(
            pool,
            ws_slug,
            filename=filename,
            data=css.encode("utf-8"),
            created_by=updated_by,
            max_bytes=max_bytes,
            mutable=True,
        )
        return {"base_id": created.id, "revision": 1, "created": True}
    if if_revision is None:
        raise HTTPException(status_code=422, detail="if_revision requis pour mettre à jour la base")
    # Garde : la cible doit bien être une base CSS (pas une maquette).
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        await _base_head(conn, wk, base_id)
    res = await mut.update_artifact(
        pool,
        ws_slug,
        base_id,
        data=css.encode("utf-8"),
        if_revision=if_revision,
        updated_by=updated_by,
        max_bytes=max_bytes,
    )
    return {"base_id": base_id, "revision": res["revision"], "created": False}


# ── Embarquement dans une maquette ────────────────────────────────────────────


async def _maquette_head(
    conn: asyncpg.Connection, wk: uuid.UUID, maquette_id: uuid.UUID
) -> asyncpg.Record:
    row = await conn.fetchrow(
        "SELECT id, revision, media_type, mutable, data FROM artifact "
        "WHERE id = $1 AND workspace_technical_key = $2",
        maquette_id,
        wk,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"maquette {maquette_id} introuvable")
    if not row["mutable"] or row["media_type"] != _MAQUETTE_MEDIA:
        raise HTTPException(status_code=422, detail="l'artefact ciblé n'est pas une maquette HTML")
    return row


async def apply_mockup_base(
    pool: asyncpg.Pool,
    ws_slug: str,
    *,
    maquette_id: uuid.UUID,
    base_id: uuid.UUID,
    updated_by: uuid.UUID | None,
    max_bytes: int,
) -> dict[str, object]:
    """Embarque (ou met à jour) le bloc de base à la version courante dans une maquette.

    - Bloc déjà présent → remplacé par `patch_artifact` (ancre = bloc existant,
      unique par construction).
    - Bloc absent → insertion avant `</head>` via `update_artifact` (remplacement
      intégral révision-gardé).
    """
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug, allow_archived=False)
        base = await _base_head(conn, wk, base_id)
        maq = await _maquette_head(conn, wk, maquette_id)
        base_rev = base["revision"]
        css = bytes(base["data"]).decode("utf-8")
        html = bytes(maq["data"]).decode("utf-8")
        maq_rev = maq["revision"]

    new_block = build_block(base_id, base_rev, css)
    existing = find_block(html, base_id)
    if existing is not None:
        old_block, cur_rev = existing
        if cur_rev == base_rev and old_block == new_block:
            return {
                "maquette_id": maquette_id,
                "revision": maq_rev,
                "base_rev": base_rev,
                "changed": False,
            }
        res = await mut.patch_artifact(
            pool,
            ws_slug,
            maquette_id,
            edits=[{"old_str": old_block, "new_str": new_block}],
            if_revision=maq_rev,
            updated_by=updated_by,
            max_bytes=max_bytes,
        )
    else:
        res = await mut.update_artifact(
            pool,
            ws_slug,
            maquette_id,
            data=_insert_block(html, new_block).encode("utf-8"),
            if_revision=maq_rev,
            updated_by=updated_by,
            max_bytes=max_bytes,
        )
    return {
        "maquette_id": maquette_id,
        "revision": res["revision"],
        "base_rev": base_rev,
        "changed": True,
    }


# ── Découverte des maquettes d'une base ───────────────────────────────────────


async def _maquettes_of_base(
    conn: asyncpg.Connection, wk: uuid.UUID, base_id: uuid.UUID
) -> list[asyncpg.Record]:
    """Maquettes HTML mutables du workspace portant le marqueur de cette base.

    Filtre SQL sur le contenu décodé (la référence vit embarquée dans le HTML,
    pas dans une colonne) : le seul lien maquette→base est le marqueur lui-même.
    """
    return list(
        await conn.fetch(
            "SELECT id, filename, revision, data FROM artifact "
            "WHERE workspace_technical_key = $1 AND media_type = $2 AND mutable "
            "  AND position($3 in convert_from(data, 'UTF8')) > 0 "
            "ORDER BY filename, id",
            wk,
            _MAQUETTE_MEDIA,
            f'data-mockup-base="{base_id}"',
        )
    )


async def mockup_base_drift(
    pool: asyncpg.Pool, ws_slug: str, base_id: uuid.UUID
) -> dict[str, object]:
    """Liste les maquettes de la base et leur état vis-à-vis de la version courante."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        base = await _base_head(conn, wk, base_id)
        current = base["revision"]
        rows = await _maquettes_of_base(conn, wk, base_id)
    maquettes: list[dict[str, object]] = []
    for r in rows:
        found = find_block(bytes(r["data"]).decode("utf-8"), base_id)
        embedded = found[1] if found else None
        maquettes.append(
            {
                "maquette_id": r["id"],
                "filename": r["filename"],
                "embedded_rev": embedded,
                "up_to_date": embedded == current,
            }
        )
    stale = [m for m in maquettes if not m["up_to_date"]]
    return {
        "base_id": base_id,
        "current_rev": current,
        "total": len(maquettes),
        "stale": len(stale),
        "maquettes": maquettes,
    }


async def propagate_mockup_base(
    pool: asyncpg.Pool,
    ws_slug: str,
    base_id: uuid.UUID,
    *,
    updated_by: uuid.UUID | None,
    max_bytes: int,
) -> dict[str, object]:
    """Réécrit le bloc de base à la version courante dans toutes les maquettes en retard.

    Une maquette qui échoue (conflit de révision, corruption) n'interrompt pas
    les autres : chaque cas est consigné et la propagation continue.
    """
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug, allow_archived=False)
        base = await _base_head(conn, wk, base_id)
        current = base["revision"]
        css = bytes(base["data"]).decode("utf-8")
        rows = await _maquettes_of_base(conn, wk, base_id)

    new_block = build_block(base_id, current, css)
    updated: list[dict[str, object]] = []
    skipped: list[uuid.UUID] = []
    failed: list[dict[str, object]] = []

    for r in rows:
        try:
            found = find_block(bytes(r["data"]).decode("utf-8"), base_id)
            if found is None:
                continue
            old_block, embedded = found
            if embedded == current:
                skipped.append(r["id"])
                continue
            await mut.patch_artifact(
                pool,
                ws_slug,
                r["id"],
                edits=[{"old_str": old_block, "new_str": new_block}],
                if_revision=r["revision"],
                updated_by=updated_by,
                max_bytes=max_bytes,
            )
            updated.append({"maquette_id": r["id"], "from_rev": embedded, "to_rev": current})
        except HTTPException as exc:
            failed.append({"maquette_id": r["id"], "error": str(exc.detail)})

    return {
        "base_id": base_id,
        "current_rev": current,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
    }
