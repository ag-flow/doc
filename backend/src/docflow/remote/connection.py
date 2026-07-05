from __future__ import annotations

import asyncio
import base64
import os
import pathlib

import asyncpg

from docflow.remote import service as rp_svc

# Scratch de clés privées déchiffrées — partagé avec le worker de backup
# (même répertoire, même durée de vie : écrit juste avant connexion, supprimé
# juste après via delete_key_file).
_KEY_SCRATCH_DIR = pathlib.Path("/data/backup-repos/keys")


def _write_private_key(key_path: pathlib.Path, private_key: str) -> None:
    """Écrit la clé privée SSH déchiffrée avec permissions 0600 dès la création.

    `write_text` puis `chmod` laisse une fenêtre world-readable (permissions
    umask, typiquement 644) entre la création et le chmod : on ouvre le
    fichier directement avec le mode final via `os.open`.
    """
    key_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(private_key)


def delete_key_file(key_path: str) -> None:
    """Supprime la clé privée temporaire — ne doit jamais rester sur disque après usage."""
    pathlib.Path(key_path).unlink(missing_ok=True)


async def resolve_git_auth(
    pool: asyncpg.Pool, remote_point_slug: str, settings: object
) -> tuple[str, str | None, dict[str, str]]:
    """Retourne (remote_url, ssh_key_path | None, git_env).

    Le PAT n'est JAMAIS mis dans l'URL du remote (persistée en clair dans
    `.git/config`) ni dans l'argv de git. Il est fourni à git via un en-tête
    `http.extraHeader: Authorization: Basic …` passé par l'environnement du
    process (`GIT_CONFIG_COUNT/KEY_0/VALUE_0`, git ≥ 2.31) : non persisté sur
    disque, absent de l'argv. `git_env` contient ces variables (vide pour SSH).
    """
    fernet_key_obj = getattr(settings, "encryption_key", None)
    fernet_key: str | None = fernet_key_obj.reveal() if fernet_key_obj else None
    harpocrate_url: str | None = getattr(settings, "harpocrate_url", None)

    point = await rp_svc.get_point(pool, remote_point_slug)

    # Construction de l'URL distante
    provider = point.git_provider or "custom"
    host = point.host
    repo = point.git_repo or ""
    if provider == "github":
        git_host = "github.com"
    elif provider == "gitlab":
        git_host = "gitlab.com"
    else:
        git_host = host
    base_url = f"{git_host}/{repo}.git"

    if point.auth_type == "certificate":
        # SSH — clé privée déchiffrée et écrite dans un fichier temporaire
        if not fernet_key:
            raise RuntimeError("encryption_key non configurée")
        assert point.certificate_slug
        private_key = await rp_svc.get_certificate_private_key(
            pool, point.certificate_slug, fernet_key
        )
        key_path = _KEY_SCRATCH_DIR / f"{point.certificate_slug}.pem"
        await asyncio.to_thread(_write_private_key, key_path, private_key)
        # Syntaxe scp-like : `:` (pas `/`) après le host, sinon git traite la
        # chaîne comme un chemin local et le clone échoue.
        remote_url = f"git@{git_host}:{repo}.git"
        return remote_url, str(key_path), {}

    # PAT : HTTPS, token injecté par en-tête via l'environnement (jamais dans
    # l'URL ni l'argv persistant).
    secret: str
    if point.auth_storage == "vault":
        from docflow.secrets.resolver import resolve
        from docflow.secrets.secret import Secret

        enc_key_obj = getattr(settings, "encryption_key", None)
        enc_key: str | None = enc_key_obj.reveal() if enc_key_obj else None
        secret = await resolve(
            Secret(point.auth_vault_ref or ""),
            harpocrate_url=harpocrate_url,
            pool=pool,
            enc_key=enc_key,
        )
    else:
        if not fernet_key:
            raise RuntimeError("encryption_key non configurée")
        secret = await rp_svc.get_point_secret(pool, remote_point_slug, fernet_key)

    remote_url = f"https://{base_url}"
    token_b64 = base64.b64encode(f"{point.username}:{secret}".encode()).decode()
    git_env = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {token_b64}",
    }
    return remote_url, None, git_env


async def resolve_dump_auth(
    pool: asyncpg.Pool, remote_point_slug: str, settings: object
) -> tuple[str, int | None, str, str | None, str | None]:
    """Retourne (host, port, username, password_or_None, ssh_key_path_or_None)."""
    fernet_key_obj = getattr(settings, "encryption_key", None)
    fernet_key: str | None = fernet_key_obj.reveal() if fernet_key_obj else None
    harpocrate_url: str | None = getattr(settings, "harpocrate_url", None)

    point = await rp_svc.get_point(pool, remote_point_slug)

    if point.auth_type == "certificate":
        if not fernet_key:
            raise RuntimeError("encryption_key non configurée")
        assert point.certificate_slug
        private_key = await rp_svc.get_certificate_private_key(
            pool, point.certificate_slug, fernet_key
        )
        key_path = _KEY_SCRATCH_DIR / f"{point.certificate_slug}.pem"
        await asyncio.to_thread(_write_private_key, key_path, private_key)
        return point.host, point.port, point.username, None, str(key_path)

    secret: str
    if point.auth_storage == "vault":
        from docflow.secrets.resolver import resolve
        from docflow.secrets.secret import Secret

        enc_key_obj = getattr(settings, "encryption_key", None)
        enc_key: str | None = enc_key_obj.reveal() if enc_key_obj else None
        secret = await resolve(
            Secret(point.auth_vault_ref or ""),
            harpocrate_url=harpocrate_url,
            pool=pool,
            enc_key=enc_key,
        )
    else:
        if not fernet_key:
            raise RuntimeError("encryption_key non configurée")
        secret = await rp_svc.get_point_secret(pool, remote_point_slug, fernet_key)

    return point.host, point.port, point.username, secret, None
