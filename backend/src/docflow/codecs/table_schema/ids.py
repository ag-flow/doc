"""Identifiants stables des champs et relations (épic MLD — F5).

Un champ peut être renommé, déplacé, retypé : son identité ne doit pas bouger,
sinon tout ce qui s'y accroche (position d'un nœud sur le canvas F7, commentaire,
lien externe) se détache au premier renommage.

**Sans recyclage** — exigence du ticket. Plutôt que d'allouer des numéros de
séquence (`f1`, `f2`…), qui obligeraient à se souvenir des numéros déjà brûlés
pour ne pas les réattribuer à un autre champ, l'identifiant est tiré au hasard
sur un espace assez large pour que la collision soit hors de portée. Le
non-recyclage devient alors une **propriété de construction**, pas une règle à
faire respecter : aucun historique à consulter, aucun compteur à persister.
"""

from __future__ import annotations

import re
import uuid

#: Préfixes : lisibles dans un diff, et suffisants pour savoir ce qu'on regarde.
FIELD_PREFIX = "fld_"
RELATION_PREFIX = "rel_"

#: 12 hex = 48 bits. Sur un schéma de quelques centaines d'entrées, la
#: probabilité de collision est négligeable ; et elle est de toute façon
#: rattrapée par le garde `taken` ci-dessous.
_HEX_LEN = 12

_ID_RE = re.compile(rf"^(?:{FIELD_PREFIX}|{RELATION_PREFIX})[0-9a-f]{{{_HEX_LEN}}}$")


def is_valid(candidate: object) -> bool:
    """Vrai si la valeur a la forme d'un identifiant alloué par docflow."""
    return isinstance(candidate, str) and bool(_ID_RE.match(candidate))


def new_id(prefix: str, taken: set[str]) -> str:
    """Alloue un identifiant neuf, absent de `taken`.

    `taken` couvre le document entier (champs ET relations) : deux entrées ne
    peuvent jamais porter le même identifiant, même de familles différentes.
    """
    while True:
        candidate = f"{prefix}{uuid.uuid4().hex[:_HEX_LEN]}"
        if candidate not in taken:
            taken.add(candidate)
            return candidate


def collect_existing(schema: dict[str, object], id_key: str) -> set[str]:
    """Identifiants déjà présents dans le document, pour ne pas les réémettre.

    Tolérant : un document à moitié écrit à la main, ou abîmé, ne doit pas faire
    échouer l'allocation. Tout ce qui n'a pas la forme attendue est ignoré ici
    et sera signalé par la validation.
    """
    taken: set[str] = set()
    for key in ("fields", "docflow.relations"):
        entries = schema.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and is_valid(entry.get(id_key)):
                taken.add(str(entry[id_key]))
    return taken
