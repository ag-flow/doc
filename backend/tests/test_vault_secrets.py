"""DoD écran Vault : usage des secrets par les automates (compteur + refus)."""

from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.schemas.vault import VaultSecretCreate
from docflow.vault import service as vault_svc


async def test_delete_secret_used_by_automation_is_refused(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """La suppression d'un secret référencé est refusée avec la liste des
    automates concernés ; le compteur d'usage est exposé au listing."""
    owner = await db_pool.fetchval(
        "INSERT INTO app_user (email, label, source, validated) "
        "VALUES ('vault-usage@example.com', 'V', 'local', true) RETURNING id"
    )
    secret = await vault_svc.create_secret(
        db_pool, owner, VaultSecretCreate(label="Clé RAG", slug="cle-rag", value="s3cret"),
        enc_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )

    wk = test_workspace["workspace_technical_key"]
    auto_id = await db_pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, event_codes, url, http_method) "
        "VALUES ($1, 'Indexe RAG', ARRAY['docflow.document.updated.v1'], 'http://x', 'POST') "
        "RETURNING id",
        wk,
    )
    await db_pool.execute(
        "INSERT INTO automation_header (automation_ref, name, secret_ref) "
        "VALUES ($1, 'Authorization', '${secret://' || $2::uuid || '}')",
        auto_id,
        secret.id,
    )

    listed = await vault_svc.list_secrets(db_pool, owner)
    assert next(s for s in listed if s.id == secret.id).used_by_automations == 1

    with pytest.raises(HTTPException) as exc:
        await vault_svc.delete_secret(db_pool, owner, secret.id)
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["automations"] == ["Indexe RAG"]

    # Un secret non référencé se supprime toujours.
    other = await vault_svc.create_secret(
        db_pool, owner, VaultSecretCreate(label="Libre", slug="libre", value="x"),
        enc_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    await vault_svc.delete_secret(db_pool, owner, other.id)
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_secret_usage_includes_webhooks(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Écart n°5 : les webhooks dont un header référence le secret comptent
    dans l'usage et bloquent la suppression, avec leur liste."""
    from docflow.crypto import encrypt_headers

    enc_key = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
    owner = await db_pool.fetchval(
        "INSERT INTO app_user (email, label, source, validated) "
        "VALUES ('vault-wh@example.com', 'V', 'local', true) RETURNING id"
    )
    secret = await vault_svc.create_secret(
        db_pool, owner, VaultSecretCreate(label="Clé WH", slug="cle-wh", value="s3cret"),
        enc_key=enc_key,
    )

    wk = test_workspace["workspace_technical_key"]
    headers = encrypt_headers(enc_key, {"Authorization": f"${{secret://{secret.id}}}"})
    await db_pool.execute(
        "INSERT INTO webhook_subscription (workspace_technical_key, label, url, "
        "headers_encrypted, events) VALUES ($1, 'Notifie CI', 'http://x', $2, "
        "ARRAY['document.created'])",
        wk,
        headers,
    )

    listed = await vault_svc.list_secrets(db_pool, owner, enc_key)
    assert next(s for s in listed if s.id == secret.id).used_by_webhooks == 1

    with pytest.raises(HTTPException) as exc:
        await vault_svc.delete_secret(db_pool, owner, secret.id, enc_key)
    assert exc.value.status_code == 409
    assert exc.value.detail["webhooks"] == ["test-ws / Notifie CI"]
