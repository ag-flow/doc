from __future__ import annotations

import re
import uuid

# Motif : jeton canonique ``dataset://<uuid>`` inséré dans le markdown par
# l'éditeur (Feature 5). La forme UUID est capturée grossièrement puis validée
# strictement via uuid.UUID(...), miroir de artifacts/parser.py.
_DATASET_TOKEN = re.compile(
    r"dataset://([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


def extract_dataset_ids(content: str | None) -> list[str]:
    """Extrait les ids de datasets référencés par un contenu markdown.

    Retourne la liste des UUID canoniques (minuscules), dédupliquée en
    conservant l'ordre de première apparition. Les ids mal formés sont ignorés
    — une référence morte ne doit jamais faire échouer un save.
    """
    if not content:
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for raw in _DATASET_TOKEN.findall(content):
        try:
            canonical = str(uuid.UUID(raw))
        except ValueError:
            continue
        if canonical not in seen:
            seen.add(canonical)
            ids.append(canonical)
    return ids
