"""API de découverte des schémas d'events (contrat producteur workflow §5).

Voie principale par laquelle le workflow acquiert (par copie) la forme des
events émis par docflow. Lecture seule ; le catalogue est statique (défini en
code, cf. events/catalog.py). Authentifié comme toute surface docflow.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from docflow.auth.deps import require_authenticated
from docflow.events import catalog
from docflow.schemas.auth import AuthUser

router = APIRouter(tags=["events"])
_Auth = Depends(require_authenticated)


@router.get("/schemas")
async def get_schema_catalog(_: AuthUser = _Auth) -> dict[str, Any]:
    """Catalogue des eventCode émis + révision pour un refresh bon marché (§5.1)."""
    return {
        "revision": catalog.catalog_revision(),
        "specVersion": catalog.SPEC_VERSION,
        "events": catalog.catalog_summary(),
    }


@router.get("/schemas/{event_code}/versions")
async def get_schema_versions(event_code: str, _: AuthUser = _Auth) -> dict[str, Any]:
    """Énumération des versions d'un eventCode (§5.3)."""
    versions = catalog.list_versions(event_code)
    if versions is None:
        raise HTTPException(status_code=404, detail=f"eventCode '{event_code}' inconnu")
    return {"eventCode": event_code, "versions": versions}


@router.get("/schemas/{event_code}/versions/{version}")
async def get_schema_version(event_code: str, version: int, _: AuthUser = _Auth) -> dict[str, Any]:
    """JSON Schema des champs métier d'une version précise (§5.2)."""
    schema = catalog.get_schema(event_code, version)
    if schema is None:
        raise HTTPException(
            status_code=404,
            detail=f"eventCode '{event_code}' version {version} inconnu",
        )
    return schema
