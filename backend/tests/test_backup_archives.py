from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from docflow.backup.archives import (
    list_ftp_archives,
    list_sftp_archives,
    parse_dump_filename,
)
from docflow.backup.db_dump import _dump_filename

_JOB_ID = uuid.UUID("12345678-90ab-cdef-1234-567890abcdef")


# ── parse_dump_filename ───────────────────────────────────────────────────────


def test_parse_roundtrip_from_dump_filename() -> None:
    """Le nom produit par _dump_filename est parseable et porte date + id complet."""
    name = _dump_filename("my-ws", _JOB_ID)
    parsed = parse_dump_filename(name)
    assert parsed is not None
    assert parsed["scope"] == "my-ws"
    assert parsed["job_id"] == str(_JOB_ID)
    assert parsed["created_at"].tzinfo is not None


def test_parse_scope_all() -> None:
    parsed = parse_dump_filename(f"docflow_all_20260708_143022_{_JOB_ID}.dump")
    assert parsed is not None
    assert parsed["scope"] == "all"
    assert parsed["created_at"] == datetime(2026, 7, 8, 14, 30, 22, tzinfo=UTC)


def test_parse_legacy_short_id() -> None:
    """Une archive héritée avec id court (8 hexas) reste parseable."""
    parsed = parse_dump_filename("docflow_ws_20260101_000000_12345678.dump")
    assert parsed is not None
    assert parsed["job_id"] == "12345678"


def test_parse_rejects_foreign_files() -> None:
    for bad in [
        "autre.dump",
        "docflow_ws_2026_143022_id.dump",  # date incomplète
        "docflow_ws_20260708_143022_XYZ.dump",  # id non hexadécimal
        "docflow_ws_20261308_143022_12345678.dump",  # mois invalide
        "readme.txt",
    ]:
        assert parse_dump_filename(bad) is None


# ── list_sftp_archives ────────────────────────────────────────────────────────


def test_list_sftp_filters_and_sizes() -> None:
    good = f"docflow_ws_20260708_143022_{_JOB_ID}.dump"

    def _attr(name: str, size: int) -> MagicMock:
        a = MagicMock()
        a.filename = name
        a.st_size = size
        return a

    mock_sftp = MagicMock()
    mock_sftp.listdir_attr.return_value = [
        _attr(good, 4096),
        _attr("notes.txt", 10),  # ignoré
    ]
    mock_ssh = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp

    with patch("paramiko.SSHClient", return_value=mock_ssh):
        out = list_sftp_archives(
            host="h",
            port=22,
            username="u",
            password="p",
            ssh_key_path=None,
            remote_dir="/backups",
        )

    assert len(out) == 1
    assert out[0]["filename"] == good
    assert out[0]["size"] == 4096
    mock_sftp.listdir_attr.assert_called_once_with("/backups")
    mock_ssh.close.assert_called_once()


# ── list_ftp_archives ─────────────────────────────────────────────────────────


def test_list_ftp_filters_and_sizes() -> None:
    good = f"docflow_ws_20260708_143022_{_JOB_ID}.dump"
    mock_ftp = MagicMock()
    mock_ftp.__enter__ = MagicMock(return_value=mock_ftp)
    mock_ftp.__exit__ = MagicMock(return_value=False)
    mock_ftp.nlst.return_value = [f"/backups/{good}", "/backups/other.txt"]
    mock_ftp.size.return_value = 2048

    with patch("ftplib.FTP", return_value=mock_ftp):
        out = list_ftp_archives(
            host="h",
            port=21,
            username="u",
            password="p",
            remote_dir="/backups",
            tls=False,
        )

    assert len(out) == 1
    assert out[0]["filename"] == good
    assert out[0]["size"] == 2048
    mock_ftp.cwd.assert_called_once_with("/backups")
