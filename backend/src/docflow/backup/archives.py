"""Parsing et listing des archives de dump sur un remote point (ftp/ftps/sftp).

Fonctions de listing **bloquantes** (réseau) : à déporter via asyncio.to_thread.
Le parser `parse_dump_filename` est pur (aucune I/O) et testable seul. Le nom
d'archive est produit par `db_dump._dump_filename` :

    docflow_<scope>_<YYYYMMDD>_<HHMMSS>_<job_id>.dump

Le nom porte la date (tri) et l'id de job (regroupement). On réutilise les
connecteurs de `db_dump` pour ne pas dupliquer la logique TOFU/TLS.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import structlog

from docflow.backup.db_dump import (
    _DEFAULT_PORTS,
    _KNOWN_HOSTS_PATH,
    _connect_ftp,
    _connect_sftp,
)

log = structlog.get_logger(__name__)

# scope ∈ {'all', slug workspace} : jamais d'underscore (cf. _SLUG_RE) → les
# underscores séparent proprement les tokens. job_id : uuid complet (36) ou,
# pour d'éventuelles archives héritées, un préfixe hexadécimal court.
_DUMP_RE = re.compile(
    r"^docflow_(?P<scope>[a-z0-9-]+)_(?P<date>\d{8})_(?P<time>\d{6})_"
    r"(?P<job_id>[0-9a-f][0-9a-f-]{7,})\.dump$"
)


def parse_dump_filename(name: str) -> dict[str, Any] | None:
    """Extrait scope / date de backup / id de job d'un nom d'archive.

    Retourne None si le nom ne suit pas la convention (fichier étranger ignoré).
    """
    m = _DUMP_RE.match(name)
    if m is None:
        return None
    try:
        created_at = datetime.strptime(m["date"] + m["time"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    return {
        "filename": name,
        "scope": m["scope"],
        "job_id": m["job_id"],
        "created_at": created_at,
        "size": None,
    }


def list_sftp_archives(
    *,
    host: str,
    port: int,
    username: str,
    password: str | None,
    ssh_key_path: str | None,
    remote_dir: str | None,
    known_hosts_path: Any = _KNOWN_HOSTS_PATH,
) -> list[dict[str, Any]]:
    """Liste les archives docflow d'un répertoire SFTP (bloquant)."""
    ssh = _connect_sftp(
        host=host,
        port=port,
        username=username,
        password=password,
        ssh_key_path=ssh_key_path,
        known_hosts_path=known_hosts_path,
    )
    try:
        sftp = ssh.open_sftp()
        try:
            entries = sftp.listdir_attr(remote_dir or ".")
        finally:
            sftp.close()
    finally:
        ssh.close()

    out: list[dict[str, Any]] = []
    for entry in entries:
        parsed = parse_dump_filename(entry.filename)
        if parsed is None:
            continue
        parsed["size"] = entry.st_size
        out.append(parsed)
    return out


def list_ftp_archives(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    remote_dir: str | None,
    tls: bool,
) -> list[dict[str, Any]]:
    """Liste les archives docflow d'un répertoire FTP/FTPS (bloquant)."""
    with _connect_ftp(host=host, port=port, username=username, password=password, tls=tls) as ftp:
        if remote_dir:
            ftp.cwd(remote_dir)
        # Mode binaire requis pour que la commande SIZE soit acceptée par le serveur.
        try:
            ftp.voidcmd("TYPE I")
        except Exception:  # noqa: BLE001 — serveur exotique : on continue sans taille
            pass
        names = ftp.nlst()
        out: list[dict[str, Any]] = []
        for name in names:
            base = name.rsplit("/", 1)[-1]
            parsed = parse_dump_filename(base)
            if parsed is None:
                continue
            try:
                parsed["size"] = ftp.size(base)
            except Exception:  # noqa: BLE001 — taille indisponible : non bloquant
                parsed["size"] = None
            out.append(parsed)
    return out


def select_archives_to_purge(
    archives: list[dict[str, Any]], job_id: str, retention_count: int
) -> list[str]:
    """Noms des archives de CE job au-delà de la rétention (les plus anciennes).

    Pur : le tri s'appuie sur la date portée par le nom de fichier. Les
    archives d'autres jobs présentes dans le même répertoire ne sont jamais
    candidates.
    """
    mine = sorted(
        (a for a in archives if a["job_id"] == job_id),
        key=lambda a: a["created_at"],
        reverse=True,
    )
    return [a["filename"] for a in mine[retention_count:]]


def purge_old_archives(
    *,
    point_type: str,
    host: str,
    port: int | None,
    username: str,
    password: str | None,
    ssh_key_path: str | None,
    remote_dir: str | None,
    tls: bool,
    job_id: str,
    retention_count: int,
) -> int:
    """Supprime du remote les archives du job au-delà de `retention_count`,
    ainsi que leur fichier compagnon `.key`. Retourne le nombre de fichiers
    supprimés. Bloquant — à appeler via executor/to_thread."""
    deleted = 0
    eff_port = port or _DEFAULT_PORTS.get(point_type, 21)
    if point_type == "sftp":
        victims = select_archives_to_purge(
            list_sftp_archives(
                host=host,
                port=eff_port,
                username=username,
                password=password,
                ssh_key_path=ssh_key_path,
                remote_dir=remote_dir,
            ),
            job_id,
            retention_count,
        )
        if not victims:
            return 0
        ssh = _connect_sftp(
            host=host,
            port=eff_port,
            username=username,
            password=password,
            ssh_key_path=ssh_key_path,
            known_hosts_path=_KNOWN_HOSTS_PATH,
        )
        try:
            sftp = ssh.open_sftp()
            try:
                for name in victims:
                    for target in (name, name.removesuffix(".dump") + ".key"):
                        path = f"{remote_dir}/{target}" if remote_dir else target
                        try:
                            sftp.remove(path)
                            deleted += 1
                        except OSError:
                            pass  # .key absent (option désactivée à l'époque) — non bloquant
            finally:
                sftp.close()
        finally:
            ssh.close()
    elif point_type in ("ftp", "ftps"):
        if password is None:
            raise RuntimeError(f"mot de passe requis pour {point_type.upper()}")
        victims = select_archives_to_purge(
            list_ftp_archives(
                host=host,
                port=eff_port,
                username=username,
                password=password,
                remote_dir=remote_dir,
                tls=tls,
            ),
            job_id,
            retention_count,
        )
        if not victims:
            return 0
        with _connect_ftp(
            host=host, port=eff_port, username=username, password=password, tls=tls
        ) as ftp:
            if remote_dir:
                ftp.cwd(remote_dir)
            for name in victims:
                for target in (name, name.removesuffix(".dump") + ".key"):
                    try:
                        ftp.delete(target)
                        deleted += 1
                    except Exception:  # noqa: BLE001 — .key absent : non bloquant
                        pass
    log.info("backup_archives_purged", job_id=job_id, deleted=deleted)
    return deleted
