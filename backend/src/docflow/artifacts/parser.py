from __future__ import annotations

import re
import uuid

# Deux formes d'insertion d'un artefact dans le markdown, toutes deux comptées
# pour le refcount :
#   - image inline : ![alt](/api/workspaces/{slug}/artifacts/{uuid}) ;
#   - puce fichier : [libellé](artifact://{uuid}) (schéma df, codec artifactChip).
# Le motif matche où que la référence apparaisse ; la validation stricte de
# forme UUID est faite via uuid.UUID(...), miroir de references/parser.py.
_ARTIFACT_URL = re.compile(
    r"(?:/api/workspaces/[^/\s)]+/artifacts/|artifact://)([0-9a-fA-F-]{36})"
)


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
