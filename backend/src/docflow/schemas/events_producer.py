"""DTO de la config runtime du producteur d'events (admin superadmin).

Le secret HMAC n'est JAMAIS exposé : la sortie porte seulement un booléen
`secret_configured`. En entrée, `secret_ref` doit être une référence vault
`${vault://...}` (jamais un secret en clair), et `allowed_events` doit être un
sous-ensemble des eventCodes connus du catalogue.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from docflow.events import catalog


class EventsProducerConfigOut(BaseModel):
    """Réponse GET/PUT — `secret_ref` MASQUÉ (seul `secret_configured` fuite)."""

    enabled: bool
    ingestion_url: str | None
    source_id: str | None
    source_uri: str
    allowed_events: list[str]
    secret_configured: bool


class EventsProducerConfigUpdate(BaseModel):
    """Corps du PUT — champs optionnels (seuls les fournis sont appliqués)."""

    model_config = {"extra": "forbid"}

    enabled: bool | None = None
    ingestion_url: str | None = None
    source_id: str | None = None
    source_uri: str | None = None
    secret_ref: str | None = None
    allowed_events: list[str] | None = None

    @field_validator("allowed_events")
    @classmethod
    def _known_events(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        unknown = [c for c in v if not catalog.is_known(c)]
        if unknown:
            raise ValueError(f"eventCodes inconnus du catalogue : {unknown}")
        return v

    @field_validator("secret_ref")
    @classmethod
    def _vault_ref(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not (v.startswith("${vault://") and v.endswith("}")):
            raise ValueError("secret_ref doit être une référence vault ${vault://...}")
        return v
