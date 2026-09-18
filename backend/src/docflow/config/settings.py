from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from docflow.secrets.secret import Secret


class Settings(BaseSettings):
    # La configuration vient EXCLUSIVEMENT des variables d'environnement : pas de
    # chargement de fichier ici. Un `env_file` se résoudrait relativement au cwd,
    # donc un `.env` de développement fuirait dans les tests (et pourrait fuiter
    # en production). La commodité dev est portée par le lanceur `dev-start.sh`,
    # qui exporte `backend/.env` avant de démarrer le serveur.
    model_config = SettingsConfigDict(extra="forbid", case_sensitive=False)

    database_url: str
    jwt_secret: Secret
    # Surcharge break-glass du mode OIDC-only, pilotée par /data/.env :
    # absent (None) = suivre le réglage de la page de configuration OIDC ;
    # true = connexion locale FORCÉE active (panne OIDC) ; false = forcée
    # inactive. Ignorée tant qu'aucun utilisateur n'existe (setup wizard).
    local_login_enabled: bool | None = None
    # ── Sessions serveur opaques (remplace le jeton HS256 de l'IHM) ──
    # Fenêtre d'inactivité : glisse à chaque requête authentifiée, ferme les
    # sessions oubliées.
    session_idle_ttl_seconds: int = 12 * 3600
    # Plafond absolu depuis l'instant d'authentification, INDÉPENDANT de
    # l'activité : force une réauthentification périodique (donc une ré-évaluation
    # des droits). Sans lui, une session active en permanence ne se referme jamais.
    session_absolute_ttl_seconds: int = 24 * 3600
    # Pose l'attribut Secure sur le cookie de session. Fail closed : par défaut le
    # cookie n'est jamais renvoyé en clair. Un déploiement en http DOIT poser false
    # explicitement (dev-deploy.sh le fait pour la machine de test) — l'oubli penche
    # du bon côté : une connexion qui ne s'établit pas se voit, un cookie servi sans
    # Secure non.
    session_cookie_secure: bool = True
    # Re-liaison d'émetteur OIDC (bascule d'IdP) : FERMÉE par défaut (fail closed).
    # Ouverte explicitement le temps d'une migration (via /data/.env), elle laisse
    # le pont par email vérifié ré-ancrer un compte connu sous un NOUVEL émetteur.
    # Ne change RIEN au refus « même émetteur, sub différent » (toujours refusé).
    oidc_relink_enabled: bool = False
    # Identifiant de RESSOURCE de la surface MCP (serveur de ressources OAuth 2.1).
    # C'est la valeur que l'IdP doit placer dans `aud` d'un jeton d'accès destiné à
    # docflow : un jeton émis pour un autre serveur MCP de la stack est refusé.
    # Annoncé dans les métadonnées de ressource protégée (RFC 9728).
    oauth2_audience: str = "docflow-mcp"
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
    # Taille max d'un artefact retourné INLINE dans la réponse MCP get_artifact_data
    # (au-delà : rediriger vers get_artifact_link). base64 gonfle ~1,33x.
    artifact_inline_max_bytes: int = 1024 * 1024
    # Purge des artefacts jamais référencés (brouillons abandonnés)
    artifact_purge_after_hours: int = 24
    # Rétention de l'historique d'un artefact MUTABLE : nombre de révisions
    # conservées (la courante toujours incluse). Taillé à chaque écriture.
    # Valeur élevée = désactive de fait le nettoyage.
    artifact_revision_keep: int = 50
    # Durée de vie d'un ticket d'upload d'artefact (create_upload → PUT →
    # create_artifact). Court : le parcours s'exécute en quelques secondes.
    artifact_upload_ttl_seconds: int = 3600
    # Purge des datasets jamais référencés (brouillons abandonnés)
    dataset_purge_after_hours: int = 24
    # URL publique de l'instance (préfixe des liens signés absolus) ; None = liens relatifs
    public_base_url: str | None = None
    # Origine DÉDIÉE de rendu des maquettes HTML (ex. https://preview.yoops.org),
    # DISTINCTE de public_base_url : du HTML non fiable y est servi en iframe
    # sandboxée (CSP fermée). None = rendu des maquettes désactivé (fail closed).
    preview_base_url: str | None = None
    # ── Rendu PNG des maquettes (port optionnel) ──
    # Service de rendu HTML→PNG (contrat : POST {url}/screenshot {html, viewport}
    # → image/png ; compatible Browserless). None = PNG désactivé (dégradé assumé,
    # jamais une installation cassée). Le service DOIT être isolé (aucun réseau
    # sortant, éphémère) : il exécute du HTML non fiable (exigence anti-SSRF).
    render_service_url: str | None = None
    render_service_token: Secret | None = None
    render_timeout_seconds: int = 30

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
    # Rétention des events LIVRÉS dans l'outbox : purgés au-delà (heures). Les
    # entrées dead-letter (failed_at) sont conservées pour inspection.
    event_outbox_purge_after_hours: int = 24

    # Propagation du contexte de trace (STANDARD « Traçabilité du contexte »).
    # Suffixes d'hôtes reconnus INTERNES vers lesquels un automate propage
    # traceparent + baggage. FAIL-CLOSED : liste vide (défaut) = on ne propage
    # vers AUCUNE cible. La topologie interne ne franchit jamais une frontière
    # externe (webhook client, cible hors allowlist). Relu à chaud via Settings.
    trace_propagation_internal_hosts: list[str] = []

    # Ingress : nom de l'en-tete pose par la gateway sur un appel INTERNE
    # authentifie pour voucher le contexte de trace entrant. FAIL-CLOSED : None
    # (defaut) = aucun contexte entrant n'est jamais relaye (un appelant externe
    # / l'UI demarre un fil neuf). Trust delegue a la gateway sur le reseau
    # interne, meme modele que X-Forwarded-* (STANDARD 3/4).
    trace_ingress_header: str | None = None
