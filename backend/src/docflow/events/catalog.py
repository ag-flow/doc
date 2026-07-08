"""Catalogue des events produits par docflow (contrat producteur workflow).

Source de vérité des `_eventCode` émis et de leur `dataSchema` (forme des
champs métier, à la racine de l'enveloppe plate). Exposé via l'API de
découverte (`GET /schemas`…) pour que le workflow en copie les schémas.

Le format d'`_eventCode` est `domaine.objet.action.vN` (norme §4.1) ; le
suffixe `vN` versionne la forme des champs métier. Ici tous les events sont
en v1 ; une évolution de forme se traduira par un nouvel eventCode `.v2`
coexistant, jamais par une édition en place.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

SPEC_VERSION = "1.0"

# Champ métier réutilisés (JSON Schema fragments).
_UUID = {"type": "string", "format": "uuid"}
_UUID_OR_NULL = {"type": ["string", "null"], "format": "uuid"}
_STR = {"type": "string"}
_STR_OR_NULL = {"type": ["string", "null"]}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class EventDef:
    title: str
    description: str
    data_schema: dict[str, Any]
    latest_version: int = 1
    deprecated: bool = False


# Ordre = ordre de déclaration (préservé par dict Python 3.7+).
CATALOG: dict[str, EventDef] = {
    "docflow.document.created.v1": EventDef(
        title="Document créé",
        description="Un document a été créé dans un bloc d'un workspace.",
        data_schema=_schema(
            {
                "documentId": _UUID,
                "workspaceSlug": _STR,
                "blockSlug": _STR,
                "functionalTypeSlug": _STR_OR_NULL,
                "parentId": _UUID_OR_NULL,
                "title": _STR,
            },
            ["documentId", "workspaceSlug", "blockSlug", "title"],
        ),
    ),
    "docflow.document.updated.v1": EventDef(
        title="Document mis à jour",
        description="Le titre et/ou le contenu d'un document a changé (nouvelle version).",
        data_schema=_schema(
            {
                "documentId": _UUID,
                "workspaceSlug": _STR,
                "version": {"type": "integer"},
                "title": _STR,
            },
            ["documentId", "workspaceSlug", "version", "title"],
        ),
    ),
    "docflow.document.deleted.v1": EventDef(
        title="Document supprimé",
        description="Un document (et sa descendance) a été supprimé.",
        data_schema=_schema(
            {
                "documentId": _UUID,
                "workspaceSlug": _STR,
                "blockSlug": _STR,
                "functionalTypeSlug": _STR_OR_NULL,
            },
            ["documentId", "workspaceSlug", "blockSlug"],
        ),
    ),
    "docflow.document.propertyChanged.v1": EventDef(
        title="Propriété modifiée",
        description=(
            "La valeur d'une propriété d'un document a changé. Couvre les "
            "transitions de statut : un statut est une propriété restricted_list "
            "— filtrer sur propSlug pour cibler une propriété précise."
        ),
        data_schema=_schema(
            {
                "documentId": _UUID,
                "workspaceSlug": _STR,
                "propSlug": _STR,
                "propType": _STR,
                "value": _STR_OR_NULL,
                "allowedValueSlug": _STR_OR_NULL,
            },
            ["documentId", "workspaceSlug", "propSlug", "propType"],
        ),
    ),
    "docflow.document.moved.v1": EventDef(
        title="Document déplacé",
        description="Le parent d'un document a changé (reparentage dans le même bloc).",
        data_schema=_schema(
            {
                "documentId": _UUID,
                "workspaceSlug": _STR,
                "parentId": _UUID_OR_NULL,
            },
            ["documentId", "workspaceSlug"],
        ),
    ),
    "docflow.document.retyped.v1": EventDef(
        title="Document retypé",
        description="Le type fonctionnel d'un document a changé.",
        data_schema=_schema(
            {
                "documentId": _UUID,
                "workspaceSlug": _STR,
                "functionalTypeSlug": _STR_OR_NULL,
            },
            ["documentId", "workspaceSlug"],
        ),
    ),
}


def _sha256(data: object) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_known(event_code: str) -> bool:
    return event_code in CATALOG


def catalog_revision() -> str:
    """Empreinte du catalogue entier — change ssi un eventCode ou un schéma change."""
    snapshot = {
        code: {
            "title": d.title,
            "description": d.description,
            "latestVersion": d.latest_version,
            "deprecated": d.deprecated,
            "dataSchema": d.data_schema,
        }
        for code, d in CATALOG.items()
    }
    return _sha256(snapshot)


def catalog_summary() -> list[dict[str, Any]]:
    """Liste pour `GET /schemas` : un résumé par eventCode."""
    return [
        {
            "eventCode": code,
            "latestVersion": d.latest_version,
            "title": d.title,
            "description": d.description,
            "deprecated": d.deprecated,
        }
        for code, d in CATALOG.items()
    ]


def schema_hash(event_code: str) -> str:
    return _sha256(CATALOG[event_code].data_schema)


def get_schema(event_code: str, version: int) -> dict[str, Any] | None:
    """Schéma d'une version précise, ou None si eventCode/version inconnus."""
    d = CATALOG.get(event_code)
    if d is None or version != d.latest_version:
        return None
    return {
        "eventCode": event_code,
        "version": version,
        "dataSchema": d.data_schema,
        "hash": schema_hash(event_code),
    }


def list_versions(event_code: str) -> list[int] | None:
    d = CATALOG.get(event_code)
    if d is None:
        return None
    # Une seule version vivante par eventCode aujourd'hui ; l'API reste
    # versionnée pour accueillir une v2 future sans changer sa forme.
    return list(range(1, d.latest_version + 1))
