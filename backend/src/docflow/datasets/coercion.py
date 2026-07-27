"""Coercion et validation d'une valeur de cellule selon le type de colonne.

Fonctions PURES (aucune I/O) réutilisables par les autres features (import CSV,
tools MCP). Chaque valeur brute (texte) est projetée sur les quatre colonnes
porteuses de ``dataset_cell`` : la colonne texte ``value`` conserve toujours la
représentation d'origine, et l'OMBRE TYPÉE adéquate (``num_value`` /
``date_value`` / ``bool_value``) porte la valeur indexable pour le filtrage.
"""

from __future__ import annotations

import datetime
from typing import Literal, get_args

ColumnType = Literal["text", "int", "float", "date", "bool", "url"]

COLUMN_TYPES: tuple[ColumnType, ...] = get_args(ColumnType)

_EMPTY_CELL: dict[str, object] = {
    "value": None,
    "num_value": None,
    "date_value": None,
    "bool_value": None,
}

_BOOL_TRUE = {"true", "1", "vrai"}
_BOOL_FALSE = {"false", "0", "faux"}


def coerce_cell(col_type: ColumnType, raw: str | None) -> dict[str, object]:
    """Projette ``raw`` sur les 4 colonnes porteuses d'une cellule.

    Retourne un dict ``{"value", "num_value", "date_value", "bool_value"}`` ;
    les colonnes non concernées valent ``None``. Une valeur vide (``None`` ou
    chaîne vide/espaces) donne une cellule entièrement ``None``.

    Lève ``ValueError`` (message clair mentionnant la valeur et le type attendu)
    si ``raw`` n'est pas convertible dans ``col_type``.
    """
    if col_type not in COLUMN_TYPES:
        raise ValueError(f"type de colonne inconnu : {col_type!r}")
    if raw is None or raw.strip() == "":
        return dict(_EMPTY_CELL)

    if col_type == "text":
        return _cell(value=raw)
    if col_type == "url":
        return _coerce_url(raw)
    if col_type == "int":
        return _coerce_int(raw)
    if col_type == "float":
        return _coerce_float(raw)
    if col_type == "date":
        return _coerce_date(raw)
    return _coerce_bool(raw)


def _cell(
    *,
    value: object = None,
    num_value: object = None,
    date_value: object = None,
    bool_value: object = None,
) -> dict[str, object]:
    return {
        "value": value,
        "num_value": num_value,
        "date_value": date_value,
        "bool_value": bool_value,
    }


def _coerce_url(raw: str) -> dict[str, object]:
    lowered = raw.strip().lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        raise ValueError(
            f"valeur {raw!r} invalide pour le type 'url' : schéma http:// ou https:// attendu"
        )
    return _cell(value=raw)


def _coerce_int(raw: str) -> dict[str, object]:
    try:
        parsed = int(raw)
    except ValueError:
        raise ValueError(f"valeur {raw!r} invalide pour le type 'int' : entier attendu") from None
    return _cell(value=raw, num_value=parsed)


def _coerce_float(raw: str) -> dict[str, object]:
    try:
        parsed = float(raw)
    except ValueError:
        raise ValueError(
            f"valeur {raw!r} invalide pour le type 'float' : nombre décimal attendu"
        ) from None
    return _cell(value=raw, num_value=parsed)


def _coerce_date(raw: str) -> dict[str, object]:
    try:
        parsed = datetime.date.fromisoformat(raw.strip())
    except ValueError:
        raise ValueError(
            f"valeur {raw!r} invalide pour le type 'date' : format ISO AAAA-MM-JJ attendu"
        ) from None
    return _cell(value=raw, date_value=parsed)


def _coerce_bool(raw: str) -> dict[str, object]:
    lowered = raw.strip().lower()
    if lowered in _BOOL_TRUE:
        return _cell(value=raw, bool_value=True)
    if lowered in _BOOL_FALSE:
        return _cell(value=raw, bool_value=False)
    raise ValueError(
        f"valeur {raw!r} invalide pour le type 'bool' : true/false/1/0/vrai/faux attendu"
    )
