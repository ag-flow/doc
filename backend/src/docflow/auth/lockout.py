from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

_COUNT_LOCAL_ADMINS = """
SELECT COUNT(*) FROM app_user
WHERE password_hash IS NOT NULL
  AND disabled = false
  AND is_admin = true
  AND validated = true
  AND id != $1
"""

_IS_CONNECTABLE_LOCAL_ADMIN = """
SELECT EXISTS(
    SELECT 1 FROM app_user
    WHERE id = $1
      AND password_hash IS NOT NULL
      AND disabled = false
      AND is_admin = true
      AND validated = true
)
"""

# Clé arbitraire mais stable, dédiée à ce seul invariant : toute mutation
# susceptible de réduire le pool d'admins locaux connectables la prend avant de
# compter. Sans elle, deux transactions concurrentes lisent chacune « il en
# reste un » (READ COMMITTED masque l'écriture non commitée de l'autre), passent
# le garde et laissent zéro admin — write-skew. Un verrou consultatif suffit ici
# et se préfère à SERIALIZABLE : pas d'erreur de sérialisation à rejouer côté
# appelant, et la zone protégée est nommée plutôt que déduite des lignes lues.
_LOCKOUT_ADVISORY_KEY = 4_027_311_001


async def assert_not_last_local_admin(
    conn: asyncpg.Connection,
    exclude_id: uuid.UUID,
) -> None:
    """Raise 422 if removing/disabling exclude_id would leave no connectable local admin.

    Si exclude_id n'est pas lui-même un admin local connectable, l'opération ne peut
    pas réduire le pool d'admins connectables : le garde est no-op (sinon, une base
    sans admin local — p. ex. tout-OIDC — bloquerait toute mutation d'utilisateur).

    Must be called inside the same transaction as the modifying statement : le
    verrou est transactionnel, il ne couvre l'écriture que si elle partage la
    transaction du garde.
    """
    if not conn.is_in_transaction():
        raise RuntimeError(
            "assert_not_last_local_admin doit s'exécuter dans la transaction de l'écriture "
            "qu'il protège : hors transaction, son verrou est relâché immédiatement"
        )
    await conn.execute("SELECT pg_advisory_xact_lock($1)", _LOCKOUT_ADVISORY_KEY)
    target_is_admin: bool = await conn.fetchval(_IS_CONNECTABLE_LOCAL_ADMIN, exclude_id)
    if not target_is_admin:
        return
    remaining: int = await conn.fetchval(_COUNT_LOCAL_ADMINS, exclude_id)
    if remaining == 0:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "last_local_admin",
                "message": (
                    "Impossible : cet admin est le dernier compte local connectable "
                    "par mot de passe. Créez un autre admin local avant de modifier celui-ci."
                ),
            },
        )
