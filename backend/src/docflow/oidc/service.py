from __future__ import annotations

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.config.settings import Settings
from docflow.oidc.verify import OidcVerifyError, exchange_code, fetch_discovery, verify_id_token
from docflow.schemas.auth import AuthUser
from docflow.schemas.oidc import OidcCallbackIn, OidcConfigOut, OidcConfigSet, OidcPublicConfig
from docflow.secrets.resolver import resolve
from docflow.secrets.secret import Secret

log = structlog.get_logger(__name__)

_SELECT = """
SELECT id, issuer, client_id, client_secret_ref, enabled, disable_local_login,
       created_at, updated_at
FROM oidc_config LIMIT 1
"""


def _to_out(row: asyncpg.Record) -> OidcConfigOut:
    return OidcConfigOut(
        id=row["id"],
        issuer=row["issuer"],
        client_id=row["client_id"],
        enabled=row["enabled"],
        disable_local_login=row["disable_local_login"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def get_oidc_config(pool: asyncpg.Pool) -> OidcConfigOut | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT)
    if row is None:
        return None
    return _to_out(row)


async def get_public_config(pool: asyncpg.Pool) -> OidcPublicConfig | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT)
    if row is None or not row["enabled"]:
        return None
    return OidcPublicConfig(
        issuer=row["issuer"],
        client_id=row["client_id"],
        enabled=row["enabled"],
    )


async def get_login_config(pool: asyncpg.Pool) -> OidcPublicConfig | None:
    """Config publique enrichie de l'authorization_endpoint découvert chez l'issuer.

    C'est ce que consomme la mire de connexion pour construire la redirection
    authorization-code. La découverte reste côté serveur (cache + garde SSRF).
    """
    public = await get_public_config(pool)
    if public is None:
        return None
    try:
        discovery = await fetch_discovery(public.issuer)
    except OidcVerifyError as exc:
        log.warning("oidc_discovery_failed", reason=str(exc), exc_info=True)
        raise HTTPException(status_code=502, detail="issuer OIDC injoignable") from exc
    endpoint = str(discovery.get("authorization_endpoint", ""))
    if not endpoint:
        raise HTTPException(
            status_code=502, detail="authorization_endpoint absent du document de découverte"
        )
    return public.model_copy(update={"authorization_endpoint": endpoint})


async def local_login_disabled_by_oidc(pool: asyncpg.Pool) -> bool:
    """Mode OIDC-only effectif : le flag ne compte que si l'OIDC est activé —
    désactiver l'OIDC réactive donc automatiquement la connexion locale."""
    row = await pool.fetchrow("SELECT enabled, disable_local_login FROM oidc_config LIMIT 1")
    return bool(row and row["enabled"] and row["disable_local_login"])


async def count_admins_with_oidc(conn: asyncpg.Connection) -> int:
    """Nombre d'administrateurs ayant un ancrage OIDC actif — c.-à-d. qui se sont
    déjà connectés/liés avec succès en OIDC (l'ancrage n'est posé qu'à un login
    OIDC vérifié). C'est la preuve qu'un admin peut entrer sans le login local.
    Repris de la référence a2a (repositories/users.count_admins_with_oidc)."""
    count: int = await conn.fetchval(
        "SELECT count(*) FROM app_user "
        "WHERE is_admin AND oidc_subject IS NOT NULL AND disabled = false"
    )
    return count


async def set_oidc_config(pool: asyncpg.Pool, data: OidcConfigSet) -> OidcConfigOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Garde-fou anti-lockout (STANDARD §5) : couper la connexion locale est
            # REFUSÉ tant qu'aucun admin ne s'est connecté avec succès en OIDC sur
            # cette instance. Protège le cas le plus probable — OIDC activé mais mal
            # configuré (client_id/redirect/secret erroné) : sans cette garde, le
            # local se coupe, le 1er login OIDC échoue, et l'instance est verrouillée.
            cutting_local = data.enabled and data.disable_local_login
            if cutting_local and await count_admins_with_oidc(conn) == 0:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_oidc_admin",
                        "message": (
                            "Connexion locale non désactivable : aucun administrateur ne "
                            "s'est encore connecté via OIDC sur cette instance. Connectez-vous "
                            "une fois en OIDC avec un compte admin, puis réessayez."
                        ),
                    },
                )
            existing = await conn.fetchrow("SELECT id FROM oidc_config LIMIT 1")
            if existing is None:
                row = await conn.fetchrow(
                    """
                    INSERT INTO oidc_config
                        (issuer, client_id, client_secret_ref, enabled, disable_local_login)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, issuer, client_id, client_secret_ref,
                              enabled, disable_local_login, created_at, updated_at
                    """,
                    data.issuer,
                    data.client_id,
                    data.client_secret_ref,
                    data.enabled,
                    data.disable_local_login,
                )
            else:
                row = await conn.fetchrow(
                    """
                    UPDATE oidc_config
                    SET issuer = $1, client_id = $2, client_secret_ref = $3,
                        enabled = $4, disable_local_login = $5, updated_at = now()
                    WHERE id = $6
                    RETURNING id, issuer, client_id, client_secret_ref,
                              enabled, disable_local_login, created_at, updated_at
                    """,
                    data.issuer,
                    data.client_id,
                    data.client_secret_ref,
                    data.enabled,
                    data.disable_local_login,
                    existing["id"],
                )
    assert row is not None
    return _to_out(row)


async def handle_oidc_callback(
    pool: asyncpg.Pool, settings: Settings, body: OidcCallbackIn
) -> AuthUser:
    """Flow authorization-code : échange le code, vérifie l'id_token, provisionne
    l'app_user et le renvoie. N'émet PLUS de jeton : le routeur ouvre une session
    serveur et pose le cookie (sortie du modèle « docflow émet ses propres jetons »).

    Aucun claim n'est accepté sans vérification serveur de la signature de
    l'id_token contre le JWKS de l'issuer configuré (AUTH-01).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT)
    if row is None or not row["enabled"]:
        raise HTTPException(status_code=403, detail="OIDC non activé")
    issuer: str = row["issuer"]
    client_id: str = row["client_id"]

    enc = settings.encryption_key
    client_secret = await resolve(
        Secret(row["client_secret_ref"]),
        harpocrate_url=settings.harpocrate_url,
        pool=pool,
        enc_key=enc.reveal() if enc is not None else None,
    )
    try:
        id_token = await exchange_code(
            issuer=issuer,
            code=body.code,
            redirect_uri=body.redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
        )
        claims = await verify_id_token(
            id_token, issuer=issuer, client_id=client_id, nonce=body.nonce
        )
    except OidcVerifyError as exc:
        # Le message d'OidcVerifyError ne contient ni token, ni claims, ni secret.
        log.warning("oidc_callback_rejected", reason=str(exc), exc_info=True)
        raise HTTPException(status_code=401, detail="échec de vérification OIDC") from exc
    return await provision_user_for_verified_claims(
        pool, claims, issuer=issuer, relink_enabled=settings.oidc_relink_enabled
    )


_USER_COLS = "id, email, label, is_admin, validated, disabled"


def _assert_relink_allowed(
    *, previous_issuer: str | None, issuer: str, relink_enabled: bool, email: str
) -> None:
    """Décide si un compte déjà épinglé, rejoint par email sous un `sub` inconnu,
    est une bascule d'émetteur légitime ou une anomalie.

    LE DISCRIMINANT EST L'ÉMETTEUR, JAMAIS LE MODE. Même émetteur + sub différent =
    deux identités distinctes chez le même fournisseur → refus, quel que soit le
    mode de re-liaison. Seul un émetteur DIFFÉRENT est un scénario de migration, et
    seul celui-là peut être ouvert par le mode. Câbler la garde sur le drapeau au
    lieu de l'émetteur ferait de la fenêtre de migration une fenêtre de prise de
    contrôle de compte (repris de la référence a2a auth/oidc_identity.py)."""
    if previous_issuer == issuer:
        log.warning("oidc_sub_mismatch_rejected", email=email)
        raise HTTPException(
            status_code=401, detail="compte déjà associé à une autre identité OIDC"
        )
    if not relink_enabled:
        # Fail closed : une bascule d'émetteur est un acte d'administration, jamais
        # un effet de bord d'un login.
        log.warning(
            "oidc_issuer_change_rejected", previous_issuer=previous_issuer, issuer=issuer
        )
        raise HTTPException(
            status_code=401,
            detail=(
                "changement de fournisseur d'identité détecté : re-liaison fermée "
                "(un administrateur doit l'ouvrir le temps de la bascule)"
            ),
        )
    log.info("oidc_issuer_relinked", previous_issuer=previous_issuer, issuer=issuer)


async def provision_user_for_verified_claims(
    pool: asyncpg.Pool,
    id_token_claims: dict[str, object],
    *,
    issuer: str,
    relink_enabled: bool = False,
) -> AuthUser:
    """Provisionne ou lie l'app_user depuis des claims OIDC **déjà vérifiés**, et
    renvoie l'utilisateur (l'ouverture de session est faite par l'appelant).

    Ancrage sur le couple `(issuer, sub)` : `sub` n'est immuable que chez un
    émetteur donné. Résolution par le couple, puis pont par email vérifié
    (STANDARD §4), avec re-liaison discriminée par l'émetteur en cas de bascule.

    Ne jamais appeler avec des claims non vérifiés : la vérification de
    signature/iss/aud/exp est faite en amont par `handle_oidc_callback`.
    """
    email = str(id_token_claims.get("email", ""))
    sub = str(id_token_claims.get("sub", ""))
    name = str(id_token_claims.get("name", email))
    if not email or not sub:
        log.warning("oidc_login_rejected", reason="claims manquants", has_email=bool(email))
        raise HTTPException(status_code=422, detail="claims OIDC manquants (email/sub)")
    # email_verified peut être un booléen (standard OIDC) ou une chaîne "true" selon l'IdP.
    email_verified_raw = id_token_claims.get("email_verified")
    email_verified = email_verified_raw is True or str(email_verified_raw).lower() == "true"

    async with pool.acquire() as conn:
        async with conn.transaction():
            enabled_raw: bool | None = await conn.fetchval(
                "SELECT enabled FROM oidc_config LIMIT 1"
            )
            if not bool(enabled_raw):
                raise HTTPException(status_code=403, detail="OIDC non activé")

            # 1. Résolution par le couple (issuer, sub) — l'ancrage courant.
            user_row = await conn.fetchrow(
                f"SELECT {_USER_COLS} FROM app_user "
                "WHERE oidc_issuer = $1 AND oidc_subject = $2",
                issuer,
                sub,
            )
            if user_row is not None:
                # L'email a changé côté IdP : ne pas suivre en silence, c'est une
                # réassociation d'administration.
                if user_row["email"] != email:
                    log.warning("oidc_email_drift_rejected", user_id=str(user_row["id"]))
                    raise HTTPException(
                        status_code=401,
                        detail="l'email a changé côté fournisseur d'identité : "
                        "réassociation admin requise",
                    )
            else:
                # 2. Pont par email VÉRIFIÉ (sinon un sub attaquant portant l'email
                #    d'un compte local en prendrait le contrôle — AUTH-02).
                by_email = await conn.fetchrow(
                    f"SELECT {_USER_COLS}, oidc_issuer, oidc_subject "
                    "FROM app_user WHERE email = $1",
                    email,
                )
                if by_email is not None:
                    if not email_verified:
                        log.warning(
                            "oidc_login_rejected", reason="email non vérifié par l'IdP", email=email
                        )
                        raise HTTPException(
                            status_code=403,
                            detail="liaison OIDC refusée: email non vérifié par l'IdP",
                        )
                    # Compte déjà épinglé à une autre identité OIDC → garde de re-liaison.
                    if by_email["oidc_subject"] is not None:
                        _assert_relink_allowed(
                            previous_issuer=by_email["oidc_issuer"],
                            issuer=issuer,
                            relink_enabled=relink_enabled,
                            email=email,
                        )
                        # Bascule : on referme le couple précédent dans l'historique.
                        await conn.execute(
                            "UPDATE user_oidc_identity_history SET unlinked_at = now() "
                            "WHERE user_id = $1 AND unlinked_at IS NULL",
                            by_email["id"],
                        )
                    await conn.execute(
                        "UPDATE app_user SET oidc_issuer = $1, oidc_subject = $2, "
                        "source = 'oidc' WHERE id = $3",
                        issuer,
                        sub,
                        by_email["id"],
                    )
                    await conn.execute(
                        "INSERT INTO user_oidc_identity_history (user_id, issuer, sub) "
                        "VALUES ($1, $2, $3)",
                        by_email["id"],
                        issuer,
                        sub,
                    )
                    user_row = await conn.fetchrow(
                        f"SELECT {_USER_COLS} FROM app_user WHERE id = $1", by_email["id"]
                    )
                else:
                    # 3. Nouveau compte OIDC : non admin, non validé.
                    user_row = await conn.fetchrow(
                        f"""
                        INSERT INTO app_user
                            (email, label, oidc_issuer, oidc_subject, is_admin, validated, source)
                        VALUES ($1, $2, $3, $4, false, false, 'oidc')
                        RETURNING {_USER_COLS}
                        """,
                        email,
                        name,
                        issuer,
                        sub,
                    )
                    await conn.execute(
                        "INSERT INTO user_oidc_identity_history (user_id, issuer, sub) "
                        "VALUES ($1, $2, $3)",
                        user_row["id"],
                        issuer,
                        sub,
                    )
    assert user_row is not None
    if user_row["disabled"]:
        log.warning("oidc_login_rejected", reason="compte désactivé", email=email)
        raise HTTPException(status_code=403, detail="compte désactivé")
    if not user_row["validated"]:
        log.info("oidc_login_pending_validation", email=email)
        raise HTTPException(status_code=403, detail="PendingValidation")

    user = AuthUser(
        id=user_row["id"],
        email=user_row["email"],
        label=user_row["label"],
        is_admin=user_row["is_admin"],
        validated=user_row["validated"],
        disabled=user_row["disabled"],
    )
    await pool.execute("UPDATE app_user SET last_login_at = now() WHERE id = $1", user.id)
    return user


async def resolve_client_secret(
    pool: asyncpg.Pool,
    harpocrate_url: str | None,
    enc_key: str | None = None,
) -> str:
    """Déballe le client_secret_ref au point d'usage uniquement."""
    async with pool.acquire() as conn:
        ref: str | None = await conn.fetchval(
            "SELECT client_secret_ref FROM oidc_config WHERE enabled = true LIMIT 1"
        )
    if ref is None:
        raise HTTPException(status_code=503, detail="OIDC non configuré")
    return await resolve(Secret(ref), harpocrate_url=harpocrate_url, pool=pool, enc_key=enc_key)
