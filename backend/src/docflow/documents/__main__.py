"""CLI minimal pour documents & valeurs.

Usage:
  python -m docflow.documents list --workspace <slug>
  python -m docflow.documents list --workspace <slug> \
      --functional-type feature --prop statut --allowed-value done
  python -m docflow.documents get  --workspace <slug> --doc <uuid>
  python -m docflow.documents values --workspace <slug> --doc <uuid>
  python -m docflow.documents set-value --workspace <slug> --doc <uuid> \
      --prop <prop_slug> --value <val> [--allowed-value-slug <slug>] \
      --expected-version <n>
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

from docflow.config.settings import Settings
from docflow.db.pool import open_pool
from docflow.documents import service as svc
from docflow.schemas.property_value import PropertyValueSet


async def _run() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd, *rest = args

    def _get(flag: str, required: bool = True) -> str | None:
        try:
            idx = rest.index(flag)
            return rest[idx + 1]
        except (ValueError, IndexError):
            if required:
                print(f"flag manquant : {flag}", file=sys.stderr)
                sys.exit(1)
            return None

    settings = Settings()
    pool = await open_pool(settings.database_url)

    try:
        if cmd == "list":
            ws = _get("--workspace")
            assert ws is not None
            docs = await svc.list_documents(
                pool,
                ws,
                functional_type=_get("--functional-type", required=False),
                prop_slug=_get("--prop", required=False),
                allowed_value_slug=_get("--allowed-value", required=False),
            )
            for d in docs:
                print(
                    json.dumps(
                        {
                            "id": str(d.doc_technical_key),
                            "title": d.title,
                            "type": d.functional_type_slug,
                            "version": d.version,
                        }
                    )
                )

        elif cmd == "get":
            ws = _get("--workspace")
            raw_doc = _get("--doc")
            assert ws is not None and raw_doc is not None
            d = await svc.get_document(pool, ws, uuid.UUID(raw_doc))
            print(
                json.dumps(
                    {
                        "id": str(d.doc_technical_key),
                        "title": d.title,
                        "version": d.version,
                        "content": d.content,
                        "functional_type": d.functional_type_slug,
                    }
                )
            )

        elif cmd == "values":
            ws = _get("--workspace")
            raw_doc = _get("--doc")
            assert ws is not None and raw_doc is not None
            vals = await svc.list_property_values(pool, ws, uuid.UUID(raw_doc))
            for v in vals:
                print(
                    json.dumps(
                        {
                            "prop": v.prop_slug,
                            "version": v.version,
                            "value": v.value,
                            "allowed_value": v.allowed_value_slug,
                        }
                    )
                )

        elif cmd == "set-value":
            ws = _get("--workspace")
            raw_doc = _get("--doc")
            prop = _get("--prop")
            raw_ev = _get("--expected-version")
            assert (
                ws is not None and raw_doc is not None and prop is not None and raw_ev is not None
            )
            data = PropertyValueSet(
                value=_get("--value", required=False),
                allowed_value_slug=_get("--allowed-value-slug", required=False),
                expected_version=int(raw_ev),
            )
            result = await svc.set_property_value(pool, ws, uuid.UUID(raw_doc), prop, data)
            print(json.dumps({"prop": result.prop_slug, "version": result.version}))

        else:
            print(f"commande inconnue : {cmd}", file=sys.stderr)
            print(__doc__)
            sys.exit(1)

    finally:
        await pool.close()


asyncio.run(_run())
