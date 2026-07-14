from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from docflow.secrets.secret import Secret


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid", case_sensitive=False)

    database_url: str
    jwt_secret: Secret
    # Break-glass OIDC-only : false = mire sans connexion locale (/auth/login
    # refuse en 403). Volontairement piloté par /data/.env et non par la base :
    # en cas de panne OIDC, remettre true + redémarrer suffit à retrouver
    # l'accès local. Ignoré tant qu'aucun utilisateur n'existe (setup wizard).
    local_login_enabled: bool = True
    harpocrate_url: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Clé Fernet 32 octets base64-urlsafe pour chiffrer les headers webhook.
    # Requise pour créer des webhooks avec headers ; absence = headers interdits.
    encryption_key: Secret | None = None
    automation_tick_seconds: int = 60
    # URL de base d'une galerie de templates distante (toc.txt + *.yaml)
    gallery_url: str | None = None
    # Artefacts binaires (images collées dans les documents)
    artifact_max_bytes: int = 10 * 1024 * 1024
    # Durée de validité des liens de téléchargement signés (MCP get_artifact_link)
    artifact_link_ttl_seconds: int = 900
    # Purge des artefacts jamais référencés (brouillons abandonnés)
    artifact_purge_after_hours: int = 24
    # URL publique de l'instance (préfixe des liens signés absolus) ; None = liens relatifs
    public_base_url: str | None = None

    # ── Producteur d'events workflow (contrat producteur) ──
    # Émission activée ssi les trois sont renseignés. L'event est posté en
    # POST {workflow_ingestion_url}/events/{workflow_source_id}, signé HMAC.
    workflow_ingestion_url: str | None = None
    workflow_source_id: str | None = None
    workflow_hmac_secret: Secret | None = None
    # Valeur du champ système _source de l'enveloppe (URI-ref du producteur).
    event_source: str = "docflow"
    # Intervalle de balayage de l'outbox par le worker (secondes).
    event_worker_tick_seconds: int = 15
