from __future__ import annotations

import asyncio
import sys
import types
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from docflow.backup import worker
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
    # Forcer ImportError : None dans sys.modules fait échouer l'import ; un
    # simple pop ne suffit pas (le module installé serait ré-importé, et le
    # test évaluerait le vrai cron — flaky dans la minute :00 de chaque heure).
    original = sys.modules.pop("croniter", None)
    sys.modules["croniter"] = None  # type: ignore[assignment]
    try:
        result = _is_due(_job(schedule_cron="0 * * * *"), now)
    finally:
        if original is not None:
            sys.modules["croniter"] = original
        else:
            sys.modules.pop("croniter", None)
    assert result is False


# ── ni l'un ni l'autre ───────────────────────────────────────────────────────


def test_is_due_no_schedule() -> None:
    """Sans schedule, jamais dû."""
    now = datetime.now(tz=UTC)
    assert _is_due(_job(), now) is False


# ── Référence forte sur les tasks de fond ──────────────────────────────────────


async def test_spawn_job_keeps_strong_reference_until_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_spawn_job` doit garder la task dans `_background_tasks` (référence
    forte, sinon GC possible en plein vol) et la retirer une fois terminée."""
    release = asyncio.Event()

    async def _fake_run_job(
        pool: object, job: dict[str, Any], settings: object, *, run_id: object = None
    ) -> None:
        await release.wait()

    monkeypatch.setattr(worker, "run_job", _fake_run_job)

    task = worker._spawn_job(pool=object(), job={"slug": "job-x"}, settings=object())
    assert task in worker._background_tasks

    release.set()
    await task
    await asyncio.sleep(0)  # laisse le done_callback s'exécuter
    assert task not in worker._background_tasks
