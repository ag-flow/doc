from __future__ import annotations

import sys
import types
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from docflow.backup.worker import _is_due


def _job(
    *,
    schedule_every_seconds: int | None = None,
    schedule_cron: str | None = None,
    last_run_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "schedule_every_seconds": schedule_every_seconds,
        "schedule_cron": schedule_cron,
        "last_run_at": last_run_at,
    }


# ── schedule_every_seconds ────────────────────────────────────────────────────


def test_is_due_interval_first_run() -> None:
    """Sans exécution précédente le job est immédiatement dû."""
    now = datetime.now(tz=UTC)
    assert _is_due(_job(schedule_every_seconds=3600), now) is True


def test_is_due_interval_elapsed() -> None:
    now = datetime.now(tz=UTC)
    last = now - timedelta(seconds=3601)
    assert _is_due(_job(schedule_every_seconds=3600, last_run_at=last), now) is True


def test_is_due_interval_exactly_at_boundary() -> None:
    """Exactement à la limite (>=) → dû."""
    now = datetime.now(tz=UTC)
    last = now - timedelta(seconds=3600)
    assert _is_due(_job(schedule_every_seconds=3600, last_run_at=last), now) is True


def test_is_due_interval_not_elapsed() -> None:
    now = datetime.now(tz=UTC)
    last = now - timedelta(seconds=100)
    assert _is_due(_job(schedule_every_seconds=3600, last_run_at=last), now) is False


def test_is_due_interval_just_before_boundary() -> None:
    now = datetime.now(tz=UTC)
    last = now - timedelta(seconds=3599)
    assert _is_due(_job(schedule_every_seconds=3600, last_run_at=last), now) is False


# ── schedule_cron ─────────────────────────────────────────────────────────────


def _inject_mock_croniter(match_return: bool) -> tuple[types.ModuleType, MagicMock]:
    """Injecte un module croniter fictif dans sys.modules et retourne (module, cls_mock)."""
    mock_cls = MagicMock()
    mock_cls.match.return_value = match_return
    mock_mod = types.ModuleType("croniter")
    mock_mod.croniter = mock_cls  # type: ignore[attr-defined]
    sys.modules["croniter"] = mock_mod
    return mock_mod, mock_cls


def test_is_due_cron_match(monkeypatch: object) -> None:
    """croniter.match retourne True → job dû."""
    now = datetime.now(tz=UTC)
    _, mock_cls = _inject_mock_croniter(True)
    try:
        result = _is_due(_job(schedule_cron="0 * * * *"), now)
    finally:
        sys.modules.pop("croniter", None)

    assert result is True
    mock_cls.match.assert_called_once_with("0 * * * *", now)


def test_is_due_cron_no_match() -> None:
    now = datetime.now(tz=UTC)
    _inject_mock_croniter(False)
    try:
        result = _is_due(_job(schedule_cron="0 0 * * *"), now)
    finally:
        sys.modules.pop("croniter", None)

    assert result is False


def test_is_due_cron_import_error() -> None:
    """Si croniter n'est pas installé, _is_due retourne False sans lever d'exception."""
    now = datetime.now(tz=UTC)
    # Forcer ImportError en masquant le module
    original = sys.modules.pop("croniter", None)
    try:
        result = _is_due(_job(schedule_cron="0 * * * *"), now)
    finally:
        if original is not None:
            sys.modules["croniter"] = original
    assert result is False


# ── ni l'un ni l'autre ───────────────────────────────────────────────────────


def test_is_due_no_schedule() -> None:
    """Sans schedule, jamais dû."""
    now = datetime.now(tz=UTC)
    assert _is_due(_job(), now) is False
