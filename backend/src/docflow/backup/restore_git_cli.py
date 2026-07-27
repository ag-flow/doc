"""Point d'entrée CLI de la restauration du miroir git.

python -m docflow.backup.restore_git_cli /chemin/du/clone [--workspace slug]
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

from docflow.backup.restore_git import restore_tree
from docflow.config.settings import Settings
from docflow.db.pool import open_pool


async def _run(base: pathlib.Path, workspace: str | None) -> int:
    settings = Settings()  # chargé depuis l'environnement
    pool = await open_pool(settings.database_url)
    try:
        report = await restore_tree(pool, base, only_workspace=workspace)
    finally:
        await pool.close()
    print(
        f"workspaces créés : {report.workspaces_created}\n"
        f"blocs créés      : {report.blocks_created}\n"
        f"imports de types : {report.types_imported}\n"
        f"documents créés  : {report.docs_created}\n"
        f"documents màj    : {report.docs_updated}"
    )
    for err in report.errors:
        print(f"ERREUR : {err}", file=sys.stderr)
    return 1 if report.errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Restaure un miroir git_sync vers docflow")
    parser.add_argument("base", type=pathlib.Path, help="racine du clone (contient les workspaces)")
    parser.add_argument("--workspace", default=None, help="restaurer uniquement ce workspace")
    args = parser.parse_args()
    if not args.base.is_dir():
        parser.error(f"répertoire introuvable : {args.base}")
    raise SystemExit(asyncio.run(_run(args.base, args.workspace)))


if __name__ == "__main__":
    main()
