from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

import yaml

from docflow.config.settings import Settings
from docflow.db.pool import open_pool
from docflow.templates.importer import ImportConflictError, VersionConflictError, run_import
from docflow.templates.models import Template


def _load_template(path: pathlib.Path) -> Template:
    with path.open() as f:
        raw = yaml.safe_load(f)
    return Template.model_validate(raw)


def _print_report(report: object) -> None:
    from docflow.templates.importer import ImportReport

    assert isinstance(report, ImportReport)
    if report.no_op:
        print("✓ no-op : même version déjà importée, rien à faire.")
        return

    diff = report.diff
    if diff.adds:
        print(f"Ajouts ({len(diff.adds)}) :")
        for item in diff.adds:
            print(f"  + {item.path}")
    if diff.soft_updates:
        print(f"Mises à jour douces ({len(diff.soft_updates)}) :")
        for item in diff.soft_updates:
            print(f"  ~ {item.path}")
    if diff.conflicts:
        print(f"Conflits ({len(diff.conflicts)}) :", file=sys.stderr)
        for item in diff.conflicts:
            print(f"  ! {item.path} — {item.detail}", file=sys.stderr)

    if report.dry_run:
        print("(dry-run — rien n'a été écrit)")
    elif report.applied:
        print("✓ Import appliqué.")


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Import d'un template YAML dans un workspace docflow"
    )
    parser.add_argument("--workspace", required=True, help="Slug du workspace cible")
    parser.add_argument(
        "--file", required=True, type=pathlib.Path,
        help="Chemin vers le fichier YAML du template",
    )
    parser.add_argument("--dry-run", action="store_true", help="Analyse sans écriture")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"Fichier introuvable : {args.file}", file=sys.stderr)
        sys.exit(1)

    template = _load_template(args.file)
    settings = Settings()
    pool = await open_pool(settings.database_url)

    try:
        report = await run_import(pool, args.workspace, template, dry_run=args.dry_run)
        _print_report(report)
        sys.exit(0)
    except VersionConflictError as e:
        print(f"Erreur de version : {e}", file=sys.stderr)
        sys.exit(2)
    except ImportConflictError as e:
        print(str(e), file=sys.stderr)
        sys.exit(3)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(4)
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
