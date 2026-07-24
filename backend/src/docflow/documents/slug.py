"""Génération du slug d'instance d'un document : dérivation + unicité fratrie.

Quand un document est créé sans slug explicite (ex. `sync_child_documents` pour
les instances capture), on dérive un slug du titre et on le rend UNIQUE au sein
de la fratrie (même parent, ou racine du workspace) par un suffixe incrémental
déterministe : `base`, `base-2`, `base-3`… Un slug explicite en collision garde
le rejet 409 (intention appelant) — cette logique ne s'applique qu'au cas auto.

Le slug produit respecte `_SLUG_RE` du schéma document (2–80 car., minuscules,
chiffres, tirets, commence/finit par un alphanumérique).
"""

from __future__ import annotations

import re
import unicodedata
import uuid

import asyncpg

# Laisse la place au suffixe « -NNN » dans la limite des 80 caractères.
_MAX_BASE = 76


def document_base_slug(title: str) -> str:
    """Titre → base de slug valide (minuscules, tirets), jamais vide (fallback).

    Replie les accents (Réunion → reunion) avant de nettoyer.
    """
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)   # garde alphanum, espaces, tirets
    s = re.sub(r"\s+", "-", s)           # espaces → tirets
    s = re.sub(r"-+", "-", s).strip("-")  # collapse + trim des tirets
    s = s[:_MAX_BASE].strip("-")
    return s if len(s) >= 2 else "doc"


async def next_free_child_suffix(
    conn: asyncpg.Connection,
    wk: uuid.UUID,
    parent_id: uuid.UUID | None,
    base: str,
) -> int:
    """Suffixe libre pour `base` dans la fratrie : 0 (= `base`) ou le plus petit
    N≥2 tel que `base-N` soit libre. Portée : (workspace, parent) ou racine."""
    if parent_id is None:
        rows = await conn.fetch(
            "SELECT slug FROM document "
            "WHERE workspace_technical_key = $1 AND parent IS NULL "
            "AND slug IS NOT NULL AND (slug = $2 OR slug LIKE $2 || '-%')",
            wk,
            base,
        )
    else:
        rows = await conn.fetch(
            "SELECT slug FROM document "
            "WHERE workspace_technical_key = $1 AND parent = $2 "
            "AND slug IS NOT NULL AND (slug = $3 OR slug LIKE $3 || '-%')",
            wk,
            parent_id,
            base,
        )
    used = {r["slug"] for r in rows}
    if base not in used:
        return 0
    i = 2
    while f"{base}-{i}" in used:
        i += 1
    return i
