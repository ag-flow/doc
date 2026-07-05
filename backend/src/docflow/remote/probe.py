from __future__ import annotations

import asyncio

import asyncpg
import structlog

from docflow.remote import connection, service

log = structlog.get_logger(__name__)


async def probe_connection(pool: asyncpg.Pool, slug: str, settings: object) -> dict[str, object]:
    """Teste la connectivité + authentification d'un remote point déjà enregistré.

    N'écrit/ne lit rien côté distant au-delà de l'authentification (ls-remote
    pour git, connexion seule pour sftp/ftp/ftps). Ne touche jamais aux
    paramètres non sauvegardés : le test porte sur le point tel que persisté.
    """
    point = await service.get_point(pool, slug)
    ssh_key_path: str | None = None
    try:
        if point.point_type == "git":
            from docflow.backup.git_sync import test_git_connection

            remote_url, ssh_key_path, git_http_env = await connection.resolve_git_auth(
                pool, slug, settings
            )
            await asyncio.to_thread(
                test_git_connection,
                remote_url,
                ssh_key_path=ssh_key_path,
                git_http_env=git_http_env,
            )
        else:
            from docflow.backup.db_dump import (
                _DEFAULT_PORTS,
                test_ftp_connection,
                test_sftp_connection,
            )

            host, port, username, password, ssh_key_path = await connection.resolve_dump_auth(
                pool, slug, settings
            )
            eff_port = port or _DEFAULT_PORTS.get(point.point_type, 21)
            if point.point_type == "sftp":
                await asyncio.to_thread(
                    test_sftp_connection,
                    host=host,
                    port=eff_port,
                    username=username,
                    password=password,
                    ssh_key_path=ssh_key_path,
                )
            else:
                if not password:
                    raise RuntimeError(f"mot de passe requis pour {point.point_type.upper()}")
                await asyncio.to_thread(
                    test_ftp_connection,
                    host=host,
                    port=eff_port,
                    username=username,
                    password=password,
                    tls=(point.point_type == "ftps"),
                )
    except Exception as exc:
        log.info("remote_point_test_failed", slug=slug, point_type=point.point_type, error=str(exc))
        return {"ok": False, "detail": str(exc)}
    finally:
        if ssh_key_path:
            await asyncio.to_thread(connection.delete_key_file, ssh_key_path)

    return {"ok": True, "detail": "Connexion réussie"}
