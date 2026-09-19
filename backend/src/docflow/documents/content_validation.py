"""Refus d'un contenu invalide à la frontière de l'API (épic MLD — F9).

Le codec du type de contenu sait dire ce qui ne va pas (`ContentCodec.validate`).
Ce module traduit ce verdict en refus HTTP structuré, **identique quel que soit
le type de contenu** : un appelant n'a qu'un seul format d'erreur à savoir lire.

Séparation volontaire avec `version_writes`, qui écrit et ne refuse jamais :
restaurer une révision déjà enregistrée ne doit pas pouvoir échouer parce que
les règles ont changé depuis. Le refus appartient aux écritures utilisateur.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from docflow.codecs import CodecError, ContentCodec

#: Le contenu n'a même pas pu être lu (YAML cassé, JSON tronqué…).
CONTENT_UNPARSEABLE = "content_unparseable"
#: Contenu lisible mais sémantiquement faux (type inconnu, référence pendante…).
CONTENT_INVALID = "content_invalid"


def _issue(error: CodecError) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "path": error.path,
        "code": error.code,
        "message": error.message,
    }
    if error.allowed:
        issue["allowed"] = list(error.allowed)
    return issue


def ensure_valid(codec: ContentCodec[Any], content: str | None) -> None:
    """Lève un 422 structuré si le codec refuse ce contenu.

    Le corps du refus porte **toutes** les erreurs d'un coup (`issues`), chacune
    avec son `path` et, le cas échéant, le vocabulaire `allowed` — de quoi
    corriger en une passe plutôt qu'en autant d'allers-retours qu'il y a de
    fautes. `doc` pointe l'article de grammaire.
    """
    errors = codec.validate(content)
    if not errors:
        return

    unparseable = any(e.code == CONTENT_UNPARSEABLE for e in errors)
    code = CONTENT_UNPARSEABLE if unparseable else CONTENT_INVALID
    message = (
        "contenu illisible pour ce type de contenu"
        if unparseable
        else f"contenu invalide pour ce type de contenu ({len(errors)} erreur(s))"
    )
    detail: dict[str, Any] = {
        "code": code,
        "message": message,
        "issues": [_issue(e) for e in errors],
    }
    doc = next((e.doc for e in errors if e.doc), None)
    if doc:
        detail["doc"] = doc
    raise HTTPException(status_code=422, detail=detail)
