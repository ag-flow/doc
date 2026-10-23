"""Service du parcours « Connecter à Harpocrate » (start + callback).

Au retour du navigateur, docflow crée ATOMIQUEMENT un `user_secret`
`HARPOCRATE_API_KEY` local chiffré (= le token obtenu) + un `vault_wallet` qui
le référence — les deux ou aucun (`_insert_user_secret` + `_insert_vault_wallet`
dans UNE transaction, cf. `user_secrets.py` / `endpoints.py`).

Le `code_verifier` et la clé privée éphémère (`ConnectState`) ne quittent
JAMAIS le serveur : ils transitent chiffrés (Fernet) dans `connect_flow`
(Task B, `connect_store`), jamais vers le navigateur ni dans un log. Le token
obtenu n'est renvoyé au navigateur sous AUCUNE forme : seul un statut littéral
(`ConnectOutcome`) part dans l'URL de redirection.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from typing import Literal

import asyncpg
import httpx
import structlog
from harpocrate import connect as harpocrate_connect
from harpocrate.exceptions import ConnectError

from docflow.crypto import decrypt_str, encrypt_str
from docflow.schemas.auth import AuthUser
from docflow.vault import connect_store
from docflow.vault.endpoints import _insert_vault_wallet
from docflow.vault.user_secrets import _insert_user_secret

log = structlog.get_logger(__name__)

# Fenêtre entre `start` (PAR déposée chez Harpocrate) et `callback` (retour
# navigateur) : assez large pour un aller-retour humain (SSO, MFA...), assez
# courte pour qu'un `ConnectState` abandonné (code_verifier + clé privée
# chiffrés) ne reste pas exploitable indéfiniment en base.
_PENDING_TTL = timedelta(minutes=15)

ConnectOutcome = Literal["ok", "denied", "invalid_state", "already", "duplicate", "error"]


def _hash_state(state: str) -> str:
    """Même empreinte que `connect_store` (sha256 hex) — dupliquée ici plutôt que
    réutilisée pour ne pas dépendre d'un symbole privé d'un autre module."""
    return hashlib.sha256(state.encode()).hexdigest()


def _secret_slug_for_wallet(name: str) -> str:
    """Slug du secret local dérivé de l'alias du wallet, préfixé pour ne jamais
    entrer en collision avec un secret GENERIC que le même propriétaire aurait
    nommé pareil (les slugs partagent le même espace de noms par owner)."""
    return f"harpocrate-connect-{name}"


async def start_connect(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    name: str,
    url: str,
    description: str | None,
    redirect_uri: str,
    client_id: str,
    enc_key: str,
    now: datetime,
) -> str:
    """Dépose la demande PAR chez Harpocrate et retient l'état côté serveur.

    Retourne l'URL où envoyer le navigateur. `permissions=1` (read) et
    `ttl_days=None` sont des décisions figées (brief Task C), pas des valeurs
    à paramétrer par l'appelant.
    """
    # Nettoyage best-effort des `ConnectState` expirés : volontairement non
    # bloquant (une purge en panne ne doit jamais empêcher de se connecter) —
    # l'échec est journalisé puis ignoré, jamais relancé.
    try:
        async with pool.acquire() as conn:
            await connect_store.delete_expired(conn, now=now)
    except Exception as exc:  # noqa: BLE001 — repli best-effort volontaire, commenté
        log.warning("harpocrate_connect_cleanup_failed", error=str(exc))

    # SYNCHRONE côté SDK (requête HTTP bloquante) : hors boucle asyncio.
    # `harpocrate` est sans stubs (ignore_missing_imports) : le retour est Any,
    # d'où les conversions explicites ci-dessous pour rester strict sous mypy.
    raw_browser_url, pending = await asyncio.to_thread(
        harpocrate_connect.start,
        url,
        client_id,
        redirect_uri,
        1,  # permissions=1 (read) — décidé, pas de repli automatique en écriture
        None,  # ttl_days=None — décidé
    )
    browser_url = str(raw_browser_url)

    # `pending.to_dict()` contient code_verifier + clé privée : chiffré avant
    # stockage, jamais en clair, jamais journalisé.
    state_blob_enc = encrypt_str(enc_key, json.dumps(pending.to_dict()))
    pending_enc = encrypt_str(
        enc_key, json.dumps({"name": name, "url": url, "description": description})
    )
    async with pool.acquire() as conn:
        await connect_store.put(
            conn,
            state=pending.state,
            owner_id=user.id,
            state_blob_enc=state_blob_enc,
            pending_enc=pending_enc,
            expires_at=now + _PENDING_TTL,
        )
    return browser_url


async def finish_connect(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    state: str | None,
    code: str | None,
    error: str | None,
    enc_key: str,
    now: datetime,
) -> ConnectOutcome:
    """Traite le retour navigateur (fail-closed, ordre impératif — brief Task C).

    1. `state` absent → `invalid_state`.
    2. `state` inconnu/expiré/d'un autre owner/déjà consommé → `invalid_state`
       (ou `already` s'il est seulement déjà consommé) — `finish` SDK PAS
       appelé : un `state` qui ne nous appartient pas n'échange jamais de code.
    3. `error == "access_denied"` → on consomme, rien n'est créé.
    4. Sinon, échange du code auprès de Harpocrate ; une `ConnectError` ferme
       le flux sans rien créer (seul `error_code` est journalisé).
    5. Succès → création atomique secret + wallet + consommation, ou `duplicate`
       si l'alias existe déjà (rien n'est persisté).
    """
    if not state:
        return "invalid_state"

    async with pool.acquire() as conn:
        record = await connect_store.take_active(conn, state=state, owner_id=user.id, now=now)
        if record is None:
            # Isolation stricte (STANDARD Harpocrate) : take_active ne distingue
            # pas la cause (inconnu / expiré / autre owner / déjà consommé) pour
            # ne jamais révéler à l'appelant QUEL cas s'applique — sauf le rejeu,
            # dont le message dédié aide l'utilisateur sans rien dévoiler d'autrui.
            was_consumed = await conn.fetchval(
                "SELECT consumed_at IS NOT NULL FROM connect_flow "
                "WHERE state_hash = $1 AND owner_ref = $2",
                _hash_state(state),
                user.id,
            )
            return "already" if was_consumed else "invalid_state"

        if error == "access_denied":
            await connect_store.mark_consumed(conn, state=state, now=now)
            return "denied"

        state_blob_enc = record["state_enc"]
        pending_blob_enc = record["pending_enc"]

    # Déchiffrement HORS transaction DB (pas d'accès conn requis) : contient
    # code_verifier + clé privée, jamais journalisé.
    pending_state = harpocrate_connect.ConnectState.from_dict(
        json.loads(decrypt_str(enc_key, state_blob_enc))
    )
    pending_meta = json.loads(decrypt_str(enc_key, pending_blob_enc))

    try:
        # SYNCHRONE côté SDK (requête HTTP bloquante) : hors boucle asyncio.
        result = await asyncio.to_thread(
            harpocrate_connect.finish, pending_state, code=code, state=state
        )
    except ConnectError as exc:
        # Seul error_code est journalisé — jamais le code, le token ou le scellé.
        log.warning("harpocrate_connect_finish_failed", error_code=exc.error_code)
        async with pool.acquire() as conn:
            await connect_store.mark_consumed(conn, state=state, now=now)
        return "error"
    except httpx.HTTPError as exc:
        # Harpocrate injoignable (timeout, connexion refusée, erreur de requête) :
        # httpx.HTTPError couvre ConnectError/TimeoutException/RequestError du SDK.
        # SANS ce cas, la panne remonterait en 500 brut — pas de redirection, donc
        # pas de raison lisible pour l'utilisateur (critère 6). On consomme quand
        # même : le code OAuth est à usage unique et à durée très courte, garder le
        # flux local ne permettrait aucun rejeu utile. On ne journalise QUE le type
        # d'exception (le message httpx porte l'hôte) — jamais token/code/jwe/dkey.
        log.warning("harpocrate_connect_transport_failed", error_type=type(exc).__name__)
        async with pool.acquire() as conn:
            await connect_store.mark_consumed(conn, state=state, now=now)
        return "error"

    name = str(pending_meta["name"])
    url = str(pending_meta["url"])
    description = pending_meta.get("description")
    slug = _secret_slug_for_wallet(name)

    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                secret_id = await _insert_user_secret(
                    conn,
                    owner_id=user.id,
                    slug=slug,
                    label=f"Harpocrate — {name}",
                    value_enc=encrypt_str(enc_key, result.token),
                    secret_type="HARPOCRATE_API_KEY",
                )
                await _insert_vault_wallet(
                    conn,
                    owner_id=user.id,
                    name=name,
                    url=url,
                    description=description,
                    api_key_secret_ref=secret_id,
                )
                await connect_store.mark_consumed(conn, state=state, now=now)
        except asyncpg.UniqueViolationError:
            # L'échange a réussi mais l'alias existe déjà : rien n'est rangé
            # (transaction annulée) — message dédié plutôt qu'un succès trompeur.
            return "duplicate"
    return "ok"
