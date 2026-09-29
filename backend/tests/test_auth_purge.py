"""Purge break-glass des utilisateurs (STANDARD « Gestion des utilisateurs », U11-U17).

Ce qui est protégé ici n'est pas « la purge marche » mais **« la purge ne se
rejoue pas »**. Un flag resté armé viderait la table à chaque démarrage, et le
symptôme — des comptes qui disparaissent — serait attribué à tout sauf à un
fichier oublié. D'où les tests de REFUS, plus importants que le cas nominal.
"""

from __future__ import annotations

import pathlib
import uuid

import asyncpg
import pytest
from structlog.testing import capture_logs

from docflow.auth.purge import PurgeNotDisarmable, maybe_purge_users
from docflow.config.settings import Settings


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql://x/y",
        "jwt_secret": "s" * 32,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


async def _mk_user(pool: asyncpg.Pool) -> uuid.UUID:
    uid: uuid.UUID = await pool.fetchval(
        "INSERT INTO app_user (email, label, password_hash, is_admin, validated) "
        "VALUES ($1, $1, 'x', true, true) RETURNING id",
        f"purge-{uuid.uuid4().hex[:8]}@example.test",
    )
    return uid


# ── Le cas courant ne fait rien, et ne dit rien ──────────────────────────────


async def test_flag_absent_ne_purge_rien_et_ne_journalise_rien(db_pool: asyncpg.Pool) -> None:
    await _mk_user(db_pool)
    before = await db_pool.fetchval("SELECT count(*) FROM app_user")
    with capture_logs() as cap:
        assert await maybe_purge_users(db_pool, _settings()) == 0
    assert await db_pool.fetchval("SELECT count(*) FROM app_user") == before
    # Le chemin nominal ne doit produire AUCUN bruit : un log par démarrage sur un
    # geste qui n'a pas eu lieu rendrait le vrai événement invisible.
    assert cap == []


# ── Les refus : on ne purge pas si on ne peut pas désarmer ───────────────────


async def test_refus_sans_chemin_de_runtime(db_pool: asyncpg.Pool) -> None:
    """Sans fichier à réécrire, la purge serait perpétuelle."""
    uid = await _mk_user(db_pool)
    with pytest.raises(PurgeNotDisarmable, match="RUNTIME_ENV_PATH"):
        await maybe_purge_users(db_pool, _settings(prune_users=True))
    # Et surtout : rien n'a été supprimé.
    assert await db_pool.fetchval("SELECT 1 FROM app_user WHERE id = $1", uid) == 1


async def test_refus_si_le_fichier_n_existe_pas(
    db_pool: asyncpg.Pool, tmp_path: pathlib.Path
) -> None:
    uid = await _mk_user(db_pool)
    absent = tmp_path / "pas-la.env"
    with pytest.raises(PurgeNotDisarmable, match="aucun fichier"):
        await maybe_purge_users(
            db_pool, _settings(prune_users=True, runtime_env_path=str(absent))
        )
    assert await db_pool.fetchval("SELECT 1 FROM app_user WHERE id = $1", uid) == 1


async def test_refus_si_le_fichier_n_est_pas_inscriptible(
    db_pool: asyncpg.Pool, tmp_path: pathlib.Path
) -> None:
    """Les permissions sont testées par une écriture RÉELLE, pas déduites du mode."""
    uid = await _mk_user(db_pool)
    env = tmp_path / "ro.env"
    env.write_text("PRUNE_USERS=true\n")
    env.chmod(0o444)
    try:
        with pytest.raises(PurgeNotDisarmable, match="inscriptible"):
            await maybe_purge_users(
                db_pool, _settings(prune_users=True, runtime_env_path=str(env))
            )
        assert await db_pool.fetchval("SELECT 1 FROM app_user WHERE id = $1", uid) == 1
    finally:
        env.chmod(0o644)


# ── Le cas nominal, et son désarmement ───────────────────────────────────────


async def test_purge_vide_la_table_journalise_le_compte_et_desarme(
    db_pool: asyncpg.Pool, tmp_path: pathlib.Path
) -> None:
    await _mk_user(db_pool)
    await _mk_user(db_pool)
    env = tmp_path / "runtime.env"
    env.write_text("JWT_SECRET=abc\nPRUNE_USERS=true\nOTHER=keep\n")

    with capture_logs() as cap:
        removed = await maybe_purge_users(
            db_pool, _settings(prune_users=True, runtime_env_path=str(env))
        )

    assert removed >= 2
    assert await db_pool.fetchval("SELECT count(*) FROM app_user") == 0

    purged = [line for line in cap if line["event"] == "users_purged"]
    assert len(purged) == 1
    assert purged[0]["rows"] == removed
    # `warning` : c'est une destruction de données, pas une étape de démarrage.
    assert purged[0]["log_level"] == "warning"

    # Désarmé — et les autres clés du fichier sont intactes.
    content = env.read_text()
    assert "PRUNE_USERS=false" in content
    assert "JWT_SECRET=abc" in content and "OTHER=keep" in content


async def test_rejouer_le_demarrage_ne_purge_pas_une_seconde_fois(
    db_pool: asyncpg.Pool, tmp_path: pathlib.Path
) -> None:
    """Le cœur du ticket : one-shot PAR CONSTRUCTION, pas par discipline."""
    await _mk_user(db_pool)
    env = tmp_path / "runtime.env"
    env.write_text("PRUNE_USERS=true\n")
    settings = _settings(prune_users=True, runtime_env_path=str(env))

    assert await maybe_purge_users(db_pool, settings) >= 1

    # Deuxième démarrage : le processus relit le fichier désarmé, donc `prune_users`
    # est faux. On le simule en reconstruisant Settings depuis le fichier réécrit.
    assert "PRUNE_USERS=false" in env.read_text()
    uid = await _mk_user(db_pool)
    second = _settings(prune_users=False, runtime_env_path=str(env))
    assert await maybe_purge_users(db_pool, second) == 0
    assert await db_pool.fetchval("SELECT 1 FROM app_user WHERE id = $1", uid) == 1


async def test_le_flag_est_pose_meme_s_il_etait_absent_du_fichier(
    db_pool: asyncpg.Pool, tmp_path: pathlib.Path
) -> None:
    """Le flag peut venir de l'environnement sans figurer dans le fichier : il faut
    l'y écrire, sinon rien ne désarme et la garde ne sert à rien."""
    await _mk_user(db_pool)
    env = tmp_path / "runtime.env"
    env.write_text("JWT_SECRET=abc\n")
    await maybe_purge_users(db_pool, _settings(prune_users=True, runtime_env_path=str(env)))
    assert "PRUNE_USERS=false" in env.read_text()


async def test_apres_purge_le_wizard_est_de_nouveau_ouvert(
    db_pool: asyncpg.Pool, tmp_path: pathlib.Path
) -> None:
    """U14 : retour à l'état premier démarrage, c'est tout l'objet du geste."""
    from docflow.setup import service as setup_service

    await _mk_user(db_pool)
    env = tmp_path / "runtime.env"
    env.write_text("PRUNE_USERS=true\n")
    await maybe_purge_users(db_pool, _settings(prune_users=True, runtime_env_path=str(env)))
    async with db_pool.acquire() as conn:
        assert await setup_service.user_count(conn) == 0
