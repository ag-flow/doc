from __future__ import annotations

import re

# Motif : [label](docflow://doc/{uuid})
# UUID : 8-4-4-4-12 hexadécimaux (36 caractères avec tirets)
_LINK = re.compile(r"\[([^\]]*)\]\(docflow://doc/([0-9a-fA-F-]{36})\)")


def extract_references(markdown: str) -> dict[str, str]:
    """Extrait les références docflow://doc/{uuid} d'un texte markdown.

    Retourne {target_id: label}. Si un même id apparaît plusieurs fois,
    le dernier libellé gagne. Les ids mal formés ne matchent pas → ignorés.
    """
    refs: dict[str, str] = {}
    for label, target_id in _LINK.findall(markdown):
        refs[target_id] = label
    return refs
