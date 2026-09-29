"""Purge break-glass de la table des utilisateurs (STANDARD « Gestion des utilisateurs »).

Dernier recours quand plus personne ne peut se connecter : on repart de l'état
premier démarrage — table vide, donc wizard d'inscription à nouveau ouvert — sans
toucher au reste de la base. Jusqu'ici le seul moyen était `dev-deploy.sh --reset`,
c'est-à-dire `down -v` : la base ENTIÈRE détruite. « Repartir sans utilisateur » et
« perdre tous les documents » ne devaient pas être le même geste.

Le flag est **one-shot par construction** : on le désarme après usage. C'est la
condition pour qu'il soit sûr — un flag qui reste armé purgerait à chaque
redémarrage, et le symptôme (« mes comptes disparaissent ») serait attribué à tout
sauf à un fichier oublié.

D'où la règle dure de ce module : **on ne purge pas si on ne peut pas désarmer.**
L'inscriptibilité du fichier est vérifiée AVANT la suppression, et l'absence de
chemin de runtime fait échouer le démarrage plutôt que d'armer une purge perpétuelle.
"""

from __future__ import annotations

import pathlib
import re

import asyncpg
import structlog

from docflow.config.settings import Settings

log = structlog.get_logger(__name__)

#: Clé à désarmer dans le fichier de runtime.
_FLAG = "PRUNE_USERS"


class PurgeNotDisarmable(RuntimeError):
    """La purge est demandée mais on ne pourrait pas la désarmer ensuite.

    Levée AVANT toute suppression. Faire échouer le démarrage est le comportement
    voulu : une purge qu'on ne peut pas désarmer est une perte de données à chaque
    boot, et elle serait silencieuse.
    """


def _disarm(path: pathlib.Path) -> None:
    """Réécrit `PRUNE_USERS=false` dans le fichier de runtime.

    Réécriture ligne à ligne plutôt que réécriture globale : le fichier porte
    d'autres secrets, et on ne veut ni les réordonner ni risquer d'en perdre un.
    """
    lines = path.read_text().splitlines()
    seen = False
    out: list[str] = []
    for line in lines:
        if re.match(rf"^\s*{_FLAG}\s*=", line):
            out.append(f"{_FLAG}=false")
            seen = True
        else:
            out.append(line)
    if not seen:
        out.append(f"{_FLAG}=false")
    path.write_text("\n".join(out) + "\n")


def _check_disarmable(settings: Settings) -> pathlib.Path:
    if not settings.runtime_env_path:
        raise PurgeNotDisarmable(
            f"{_FLAG}=true mais RUNTIME_ENV_PATH n'est pas défini : la purge serait "
            "rejouée à chaque démarrage. Définir RUNTIME_ENV_PATH (chemin du .env de "
            "l'instance) ou retirer le flag."
        )
    path = pathlib.Path(settings.runtime_env_path)
    if not path.is_file():
        raise PurgeNotDisarmable(
            f"{_FLAG}=true mais RUNTIME_ENV_PATH ne désigne aucun fichier : {path}"
        )
    try:
        # Test d'écriture RÉEL : les permissions POSIX ne suffisent pas à conclure
        # (montage en lecture seule, système de fichiers plein).
        with path.open("a"):
            pass
    except OSError as exc:
        raise PurgeNotDisarmable(
            f"{_FLAG}=true mais {path} n'est pas inscriptible ({exc}) : refus de purger."
        ) from exc
    return path


async def maybe_purge_users(pool: asyncpg.Pool, settings: Settings) -> int:
    """Purge la table des utilisateurs si le flag est armé. Rend le nombre supprimé.

    Retourne 0 et ne journalise rien quand le flag est absent — le cas courant ne
    doit pas produire de bruit.

    Les 13 tables qui référencent `app_user` sont en `ON DELETE CASCADE` ou
    `SET NULL` : la suppression se propage sans FK bloquante. Une transaction pour
    que l'échec ne laisse pas la table à moitié vidée.
    """
    if not settings.prune_users:
        return 0

    path = _check_disarmable(settings)

    async with pool.acquire() as conn, conn.transaction():
        rows: int = await conn.fetchval("SELECT count(*) FROM app_user") or 0
        await conn.execute("DELETE FROM app_user")

    # `warning` et non `info` : c'est une destruction de données demandée à la main.
    # Le compte est l'information qui permet de vérifier après coup que le geste a
    # porté sur ce qu'on croyait.
    log.warning("users_purged", rows=rows, runtime_env_path=str(path))

    try:
        _disarm(path)
    except OSError:
        # On a vérifié l'inscriptibilité avant de supprimer ; si l'écriture échoue
        # malgré tout, il FAUT que ce soit hurlant : au prochain boot la purge
        # recommencerait.
        log.error("users_purge_disarm_failed", path=str(path), exc_info=True)
        raise

    log.warning("users_purge_disarmed", path=str(path))
    return rows
