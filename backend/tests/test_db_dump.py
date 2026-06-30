from __future__ import annotations

import pathlib
import uuid
from unittest.mock import MagicMock, patch

import pytest

from docflow.backup.db_dump import (
    _dump_filename,
    _run_pg_dump,
    _upload_ftp,
    _upload_sftp,
    run_db_dump,
)

_JOB_ID = uuid.UUID("12345678-0000-0000-0000-000000000000")


# ── _dump_filename ────────────────────────────────────────────────────────────


def test_dump_filename_includes_scope() -> None:
    name = _dump_filename("my-ws", _JOB_ID)
    assert name.startswith("docflow_my-ws_")
    assert name.endswith(".dump")
    assert str(_JOB_ID)[:8] in name


def test_dump_filename_no_scope() -> None:
    name = _dump_filename(None, _JOB_ID)
    assert name.startswith("docflow_all_")


# ── _run_pg_dump ──────────────────────────────────────────────────────────────


def test_run_pg_dump_success(tmp_path: pathlib.Path) -> None:
    dest = tmp_path / "test.dump"

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        f = kwargs["stdout"]
        f.write(b"fake dump content")  # type: ignore[union-attr]
        f.flush()  # type: ignore[union-attr]
        return MagicMock(returncode=0)

    with patch("docflow.backup.db_dump.subprocess.run", side_effect=fake_run):
        _run_pg_dump("postgresql://user:pass@host/db", dest)

    assert dest.exists()
    assert dest.read_bytes() == b"fake dump content"


def test_run_pg_dump_failure(tmp_path: pathlib.Path) -> None:
    dest = tmp_path / "test.dump"
    mock_result = MagicMock(returncode=1, stderr=b"pg_dump: connection refused")

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        return mock_result

    with patch("docflow.backup.db_dump.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="pg_dump a échoué"):
            _run_pg_dump("postgresql://user:pass@host/db", dest)


# ── _upload_ftp ───────────────────────────────────────────────────────────────


def _make_mock_ftp() -> MagicMock:
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def test_upload_ftp_with_remote_dir(tmp_path: pathlib.Path) -> None:
    dump = tmp_path / "test.dump"
    dump.write_bytes(b"data")
    mock_ftp = _make_mock_ftp()

    with patch("ftplib.FTP", return_value=mock_ftp):
        _upload_ftp(
            dump,
            "test.dump",
            host="ftp.ex.com",
            port=21,
            username="u",
            password="p",
            remote_dir="/backups",
            tls=False,
        )

    mock_ftp.connect.assert_called_once_with("ftp.ex.com", 21, timeout=60)
    mock_ftp.login.assert_called_once_with("u", "p")
    mock_ftp.cwd.assert_called_once_with("/backups")
    mock_ftp.storbinary.assert_called_once()
    mock_ftp.prot_p.assert_not_called()


def test_upload_ftp_no_remote_dir(tmp_path: pathlib.Path) -> None:
    dump = tmp_path / "test.dump"
    dump.write_bytes(b"data")
    mock_ftp = _make_mock_ftp()

    with patch("ftplib.FTP", return_value=mock_ftp):
        _upload_ftp(
            dump,
            "test.dump",
            host="ftp.ex.com",
            port=21,
            username="u",
            password="p",
            remote_dir=None,
            tls=False,
        )

    mock_ftp.cwd.assert_not_called()
    mock_ftp.storbinary.assert_called_once()


def test_upload_ftps_calls_prot_p(tmp_path: pathlib.Path) -> None:
    dump = tmp_path / "test.dump"
    dump.write_bytes(b"data")
    mock_ftp = _make_mock_ftp()

    with patch("ftplib.FTP_TLS", return_value=mock_ftp):
        _upload_ftp(
            dump,
            "test.dump",
            host="ftp.ex.com",
            port=990,
            username="u",
            password="p",
            remote_dir=None,
            tls=True,
        )

    mock_ftp.prot_p.assert_called_once()


# ── _upload_sftp ──────────────────────────────────────────────────────────────


def test_upload_sftp_password(tmp_path: pathlib.Path) -> None:
    dump = tmp_path / "test.dump"
    dump.write_bytes(b"data")

    mock_sftp = MagicMock()
    mock_ssh = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp

    with patch("paramiko.SSHClient", return_value=mock_ssh):
        _upload_sftp(
            dump,
            "test.dump",
            host="sftp.ex.com",
            port=22,
            username="u",
            password="p",
            ssh_key_path=None,
            remote_dir="/backups",
        )

    call_kw = mock_ssh.connect.call_args[1]
    assert call_kw["password"] == "p"
    assert "key_filename" not in call_kw
    mock_sftp.put.assert_called_once_with(str(dump), "/backups/test.dump")
    mock_sftp.close.assert_called_once()
    mock_ssh.close.assert_called_once()


def test_upload_sftp_key_no_remote_dir(tmp_path: pathlib.Path) -> None:
    dump = tmp_path / "test.dump"
    dump.write_bytes(b"data")

    mock_sftp = MagicMock()
    mock_ssh = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp

    with patch("paramiko.SSHClient", return_value=mock_ssh):
        _upload_sftp(
            dump,
            "test.dump",
            host="sftp.ex.com",
            port=22,
            username="u",
            password=None,
            ssh_key_path="/data/key.pem",
            remote_dir=None,
        )

    call_kw = mock_ssh.connect.call_args[1]
    assert call_kw["key_filename"] == "/data/key.pem"
    assert "password" not in call_kw
    mock_sftp.put.assert_called_once_with(str(dump), "test.dump")


# ── run_db_dump ───────────────────────────────────────────────────────────────


def test_run_db_dump_ftp_nominal(tmp_path: pathlib.Path) -> None:
    """pg_dump + upload FTP ; le fichier temporaire est supprimé."""

    def fake_pg_dump(database_url: str, dest: pathlib.Path) -> None:
        dest.write_bytes(b"dump")

    mock_ftp = _make_mock_ftp()

    with (
        patch("docflow.backup.db_dump._run_pg_dump", side_effect=fake_pg_dump),
        patch("ftplib.FTP", return_value=mock_ftp),
    ):
        result = run_db_dump(
            job_id=_JOB_ID,
            workspace_slug="ws",
            database_url="postgresql://localhost/db",
            point_type="ftp",
            host="ftp.ex.com",
            port=None,
            username="user",
            password="pass",
            ssh_key_path=None,
            remote_dir=None,
            dumps_root=tmp_path,
        )

    assert result["files_written"] == 1
    assert result["files_deleted"] == 0
    assert result["last_change_seq"] is None
    assert "docflow_ws_" in result["commit_sha"]
    # Le fichier temporaire doit être effacé
    assert list(tmp_path.glob("*.dump")) == []


def test_run_db_dump_sftp_nominal(tmp_path: pathlib.Path) -> None:
    def fake_pg_dump(database_url: str, dest: pathlib.Path) -> None:
        dest.write_bytes(b"dump")

    mock_sftp = MagicMock()
    mock_ssh = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp

    with (
        patch("docflow.backup.db_dump._run_pg_dump", side_effect=fake_pg_dump),
        patch("paramiko.SSHClient", return_value=mock_ssh),
    ):
        result = run_db_dump(
            job_id=_JOB_ID,
            workspace_slug=None,
            database_url="postgresql://localhost/db",
            point_type="sftp",
            host="sftp.ex.com",
            port=22,
            username="user",
            password="pass",
            ssh_key_path=None,
            remote_dir="/backups",
            dumps_root=tmp_path,
        )

    assert result["files_written"] == 1
    assert "docflow_all_" in result["commit_sha"]
    assert list(tmp_path.glob("*.dump")) == []


def test_run_db_dump_pg_dump_failure_cleans_up(tmp_path: pathlib.Path) -> None:
    """En cas d'échec pg_dump, run_db_dump propage l'erreur sans laisser de fichier."""
    with patch(
        "docflow.backup.db_dump._run_pg_dump",
        side_effect=RuntimeError("pg_dump a échoué (code 1)"),
    ):
        with pytest.raises(RuntimeError, match="pg_dump a échoué"):
            run_db_dump(
                job_id=_JOB_ID,
                workspace_slug="ws",
                database_url="postgresql://localhost/db",
                point_type="ftp",
                host="ftp.ex.com",
                port=21,
                username="user",
                password="pass",
                ssh_key_path=None,
                remote_dir=None,
                dumps_root=tmp_path,
            )
    assert list(tmp_path.glob("*.dump")) == []


def test_run_db_dump_unsupported_point_type(tmp_path: pathlib.Path) -> None:
    def fake_pg_dump(database_url: str, dest: pathlib.Path) -> None:
        dest.write_bytes(b"dump")

    with patch("docflow.backup.db_dump._run_pg_dump", side_effect=fake_pg_dump):
        with pytest.raises(RuntimeError, match="type de point non supporté"):
            run_db_dump(
                job_id=_JOB_ID,
                workspace_slug="ws",
                database_url="postgresql://localhost/db",
                point_type="git",
                host="github.com",
                port=None,
                username="user",
                password=None,
                ssh_key_path=None,
                remote_dir=None,
                dumps_root=tmp_path,
            )
    assert list(tmp_path.glob("*.dump")) == []


def test_run_db_dump_ftp_missing_password(tmp_path: pathlib.Path) -> None:
    """FTP sans mot de passe → RuntimeError avant même l'upload."""

    def fake_pg_dump(database_url: str, dest: pathlib.Path) -> None:
        dest.write_bytes(b"dump")

    with patch("docflow.backup.db_dump._run_pg_dump", side_effect=fake_pg_dump):
        with pytest.raises(RuntimeError, match="mot de passe requis"):
            run_db_dump(
                job_id=_JOB_ID,
                workspace_slug="ws",
                database_url="postgresql://localhost/db",
                point_type="ftp",
                host="ftp.ex.com",
                port=21,
                username="user",
                password=None,
                ssh_key_path=None,
                remote_dir=None,
                dumps_root=tmp_path,
            )
    assert list(tmp_path.glob("*.dump")) == []
