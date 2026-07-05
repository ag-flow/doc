from __future__ import annotations

import re
import uuid

# Motif : /api/workspaces/{slug}/artifacts/{uuid} — tel qu'inséré dans le
# markdown par l'éditeur (![alt](url)). Le motif matche l'URL où qu'elle
# apparaisse (image, lien simple) ; la validation stricte de forme UUID est
# faite via uuid.UUID(...), miroir de references/parser.py.
_ARTIFACT_URL = re.compile(r"/api/workspaces/[^/\s)]+/artifacts/([0-9a-fA-F-]{36})")


def extract_artifact_ids(markdown: str) -> set[str]:
    """Extrait les ids d'artefacts référencés par un contenu markdown.

    Retourne un ensemble d'UUID canoniques (minuscules). Les ids mal formés
    sont ignorés — un lien cassé ne doit jamais faire échouer un save.
    """
    ids: set[str] = set()
    for raw in _ARTIFACT_URL.findall(markdown):
        try:
            ids.add(str(uuid.UUID(raw)))
        except ValueError:
            continue
    return ids
