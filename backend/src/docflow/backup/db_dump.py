from __future__ import annotations

import ftplib
import os
import pathlib
import subprocess
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import paramiko  # type: ignore[import-untyped]
import structlog

log = structlog.get_logger(__name__)

# `_upload_ftp` utilise ftplib.FTP_TLS, qui ne fait que du TLS explicite
# (connexion en clair puis AUTH TLS) : le port par défaut est donc 21, pas 990
# (TLS implicite, non supporté par ftplib.FTP_TLS).
_DEFAULT_PORTS = {"ftp": 21, "ftps": 21, "sftp": 22}

# Fichier known_hosts dédié au worker de backup (TOFU — trust on first use).
_KNOWN_HOSTS_PATH = pathlib.Path("/data/backup-known-hosts")


class _TofuHostKeyPolicy(paramiko.MissingHostKeyPolicy):  # type: ignore[misc]
    """Trust On First Use : épingle la clé d'un hôte SFTP inconnu.

    `AutoAddPolicy` accepte silencieusement N'IMPORTE QUELLE clé à CHAQUE
    connexion (aucune protection MITM). Ici, seule la toute première
    connexion à un hôte donné passe par `missing_host_key` (paramiko ne
    l'appelle que si l'hôte n'a pas déjà une entrée chargée) ; la clé est
    alors mémorisée sur disque. Si la clé d'un hôte déjà connu change
    ensuite, `SSHClient.connect` lève `BadHostKeyException` avant même
    d'atteindre cette policy — l'upload du dump est bloqué.
    """

    def __init__(self, known_hosts_path: pathlib.Path) -> None:
        self._known_hosts_path = known_hosts_path

    def missing_host_key(
        self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey
    ) -> None:
        log.warning(
            "sftp_host_key_tofu_pinned",
            hostname=hostname,
            fingerprint=key.get_fingerprint().hex(),
        )
        client.get_host_keys().add(hostname, key.get_name(), key)
        self._known_hosts_path.parent.mkdir(parents=True, exist_ok=True)
        client.save_host_keys(str(self._known_hosts_path))


def _dump_filename(workspace_slug: str | None, job_id: uuid.UUID) -> str:
    """Nom d'archive : `docflow_<scope>_<YYYYMMDD_HHMMSS>_<job_id>.dump`.

    Le nom porte la date du backup (tri chronologique) et l'id **complet** du job
    (regroupement non ambigu des archives d'un même job) — cf. `archives.py` pour
    le parsing/listing. Le scope ('all' ou slug de workspace) ne contient jamais
    d'underscore, ce qui garantit un découpage stable des tokens.
    """
    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    scope = workspace_slug or "all"
    return f"docflow_{scope}_{ts}_{job_id}.dump"


def _strip_password(database_url: str) -> tuple[str, str | None]:
    """Retire le mot de passe d'un DSN Postgres. Retourne (dsn_sans_mdp, mot_de_passe)."""
    parts = urlsplit(database_url)
    if parts.password is None:
        return database_url, None
    password = unquote(parts.password)  # le DSN véhicule le mot de passe percent-encodé
    netloc = quote(parts.username or "", safe="")
    if parts.hostname:
        netloc += f"@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    stripped = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return stripped, password


def _run_pg_dump(database_url: str, dest: pathlib.Path) -> None:
    """Lance pg_dump --format=custom vers dest (bloquant, appeler depuis executor).

    Le mot de passe n'est jamais passé en argv (visible via /proc/*/cmdline ou
    `ps aux`) : le DSN est nettoyé et le mot de passe injecté via l'env PGPASSWORD.
    """
    dsn, password = _strip_password(database_url)
    cmd = ["pg_dump", "--format=custom", "--no-password", f"--dbname={dsn}"]
    env = dict(os.environ)
    if password is not None:
        env["PGPASSWORD"] = password
    result = subprocess.run(  # noqa: S603
        cmd,
        stdout=dest.open("wb"),
        stderr=subprocess.PIPE,
        timeout=3600,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")
        raise RuntimeError(f"pg_dump a échoué (code {result.returncode}): {stderr[:500]}")


def _connect_ftp(*, host: str, port: int, username: str, password: str, tls: bool) -> ftplib.FTP:
    cls = ftplib.FTP_TLS if tls else ftplib.FTP
    ftp = cls()
    ftp.connect(host, port, timeout=60)
    ftp.login(username, password)
    if tls:
        ftp.prot_p()  # type: ignore[attr-defined]
    return ftp


def _ftp_makedirs(ftp: Any, remote_dir: str) -> None:
    """mkdir -p distant : descend segment par segment, crée ce qui manque."""
    if remote_dir.startswith("/"):
        ftp.cwd("/")
    for segment in (s for s in remote_dir.split("/") if s):
        try:
            ftp.cwd(segment)
        except ftplib.error_perm:
            ftp.mkd(segment)
            ftp.cwd(segment)


def _upload_ftp(
    dump_path: pathlib.Path,
    filename: str,
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    remote_dir: str | None,
    tls: bool,
) -> None:
    with _connect_ftp(host=host, port=port, username=username, password=password, tls=tls) as ftp:
        if remote_dir:
            _ftp_makedirs(ftp, remote_dir)
        with dump_path.open("rb") as f:
            ftp.storbinary(f"STOR {filename}", f)


def test_ftp_connection(*, host: str, port: int, username: str, password: str, tls: bool) -> None:
    """Connexion + authentification seules — aucune écriture distante."""
    with _connect_ftp(host=host, port=port, username=username, password=password, tls=tls):
        pass


def _connect_sftp(
    *,
    host: str,
    port: int,
    username: str,
    password: str | None,
    ssh_key_path: str | None,
    known_hosts_path: pathlib.Path,
) -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    if known_hosts_path.exists():
        ssh.load_host_keys(str(known_hosts_path))
    ssh.set_missing_host_key_policy(_TofuHostKeyPolicy(known_hosts_path))
    connect_kwargs: dict[str, Any] = {
        "hostname": host,
        "port": port,
        "username": username,
        "timeout": 60,
    }
    if ssh_key_path:
        connect_kwargs["key_filename"] = ssh_key_path
        connect_kwargs["look_for_keys"] = False
    else:
        connect_kwargs["password"] = password
        connect_kwargs["look_for_keys"] = False
    ssh.connect(**connect_kwargs)
    return ssh


def _sftp_makedirs(sftp: Any, remote_dir: str) -> None:
    """mkdir -p distant : crée chaque segment manquant du chemin (idempotent)."""
    path = "/" if remote_dir.startswith("/") else ""
    for segment in (s for s in remote_dir.split("/") if s):
        path = f"{path.rstrip('/')}/{segment}" if path else segment
        try:
            sftp.stat(path)
        except OSError:
            sftp.mkdir(path)


def _upload_sftp(
    dump_path: pathlib.Path,
    filename: str,
    *,
    host: str,
    port: int,
    username: str,
    password: str | None,
    ssh_key_path: str | None,
    remote_dir: str | None,
    known_hosts_path: pathlib.Path = _KNOWN_HOSTS_PATH,
) -> None:
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
            if remote_dir:
                _sftp_makedirs(sftp, remote_dir)
            remote_path = f"{remote_dir}/{filename}" if remote_dir else filename
            sftp.put(str(dump_path), remote_path)
        finally:
            sftp.close()
    finally:
        ssh.close()


def test_sftp_connection(
    *,
    host: str,
    port: int,
    username: str,
    password: str | None,
    ssh_key_path: str | None,
    known_hosts_path: pathlib.Path = _KNOWN_HOSTS_PATH,
) -> None:
    """Connexion + authentification seules — aucun transfert distant."""
    ssh = _connect_sftp(
        host=host,
        port=port,
        username=username,
        password=password,
        ssh_key_path=ssh_key_path,
        known_hosts_path=known_hosts_path,
    )
    try:
        ssh.open_sftp().close()
    finally:
        ssh.close()


def run_db_dump(
    *,
    job_id: uuid.UUID,
    workspace_slug: str | None,
    database_url: str,
    point_type: str,
    host: str,
    port: int | None,
    username: str,
    password: str | None,
    ssh_key_path: str | None,
    remote_dir: str | None,
    dumps_root: pathlib.Path,
) -> dict[str, Any]:
    """Exécute un pg_dump et upload le fichier sur le remote point.

    Bloquant — à appeler depuis run_in_executor.
    Retourne un dict compatible avec finish_run.
    """
    dumps_root.mkdir(parents=True, exist_ok=True)
    filename = _dump_filename(workspace_slug, job_id)
    dump_path = dumps_root / filename

    try:
        log.info("db_dump_start", job_id=str(job_id), filename=filename)
        _run_pg_dump(database_url, dump_path)
        size = dump_path.stat().st_size
        log.info("db_dump_done", filename=filename, size_bytes=size)

        eff_port = port or _DEFAULT_PORTS.get(point_type, 21)

        if point_type == "sftp":
            _upload_sftp(
                dump_path,
                filename,
                host=host,
                port=eff_port,
                username=username,
                password=password,
                ssh_key_path=ssh_key_path,
                remote_dir=remote_dir,
            )
        elif point_type in ("ftp", "ftps"):
            if not password:
                raise RuntimeError(f"mot de passe requis pour {point_type.upper()}")
            _upload_ftp(
                dump_path,
                filename,
                host=host,
                port=eff_port,
                username=username,
                password=password,
                remote_dir=remote_dir,
                tls=(point_type == "ftps"),
            )
        else:
            raise RuntimeError(f"type de point non supporté pour db_dump : {point_type!r}")

        log.info("db_dump_uploaded", filename=filename, host=host)
        return {
            "last_change_seq": None,
            "files_written": 1,
            "files_deleted": 0,
            "commit_sha": filename,
        }

    finally:
        if dump_path.exists():
            dump_path.unlink()
