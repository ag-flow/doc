from __future__ import annotations

import re

import httpx
import structlog

from docflow.secrets.secret import Secret

_VAULT_RE = re.compile(r"^\$\{vault://([^/:]+):(/.+)\}$")

log = structlog.get_logger(__name__)


async def resolve(
    secret: Secret,
    *,
    harpocrate_url: str | None,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Resolve a Secret value.

    If the value matches ${vault://apiname:/path}, fetches from Harpocrate.
    Otherwise returns the inline value unchanged (fallback inline).
    Raises ValueError when a vault ref is present but no Harpocrate URL is configured.
    """
    raw = secret.reveal()
    match = _VAULT_RE.match(raw)
    if not match:
        return raw

    if not harpocrate_url:
        raise ValueError("Secret contains a vault reference but HARPOCRATE_URL is not configured")

    api_name, path = match.group(1), match.group(2)
    url = f"{harpocrate_url.rstrip('/')}/api/{api_name}{path}"
    log.debug("resolving_vault_secret", api=api_name, path=path)

    _client = client if client is not None else httpx.AsyncClient()
    try:
        response = await _client.get(url)
        response.raise_for_status()
        return str(response.json()["value"])
    finally:
        if client is None:
            await _client.aclose()
