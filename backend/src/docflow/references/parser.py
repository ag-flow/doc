from __future__ import annotations

import re
import uuid

# Motif : [label](docflow://doc/{uuid})
# UUID : 8-4-4-4-12 hexadécimaux (36 caractères avec tirets)
# Le motif reste laxiste (36 caractères hex/tirets) ; la validation stricte de
# forme UUID est faite ci-dessous via uuid.UUID(...).
_LINK = re.compile(r"\[([^\]]*)\]\(docflow://doc/([0-9a-fA-F-]{36})\)")


def extract_references(markdown: str) -> dict[str, str]:
    """Extrait les références docflow://doc/{uuid} d'un texte markdown.

    Retourne {target_id: label} avec target_id normalisé en UUID canonique
    (minuscules, tirets aux bonnes positions). Si un même id (à la casse
    près) apparaît plusieurs fois, le dernier libellé gagne. Les ids mal
    formés (pas un UUID valide) sont ignorés.
    """
    refs: dict[str, str] = {}
    for label, target_id in _LINK.findall(markdown):
        try:
            canonical = str(uuid.UUID(target_id))
        except ValueError:
            continue
        refs[canonical] = label
    return refs
