"""Pré-condition d'un automate : interroger la cible avant d'agir.

Un automate ne savait qu'appeler ; il ne pouvait ni vérifier, ni s'abstenir.
Deux pannes réelles en découlaient (2026-10-08) : un `409 Conflict` à chaque
tentative de créer un workspace RAG déjà présent, et un `404` à l'indexation
d'un document dont le corpus n'existait pas encore — ce dernier épuisant ses
tentatives jusqu'au dead-letter.

La condition est de la **donnée, pas un langage** : une liste de règles
ordonnées, chacune testant le code HTTP et/ou une valeur du corps par égalité.
Pas de grammaire à spécifier, à valider ni à outiller dans l'écran ; le jeu de
critères s'élargit sans rien casser, l'inverse serait faux.

Trois issues, et elles ne sont pas interchangeables :

- `proceed` — faire l'appel principal ;
- `skip`    — ne pas l'appeler, et tenir l'event pour traité ;
- `defer`   — ne pas l'appeler, et revenir plus tard : ni consommé, ni en échec.

La distinction `skip` / `defer` est ce qui sépare les deux cas réels. Créer une
ressource qui existe déjà est un non-événement (`skip`) ; indexer dans un corpus
absent est une attente (`defer`). Les confondre ramène soit le 409, soit le
dead-letter.
"""

from __future__ import annotations

import json
from typing import Any, Literal

Outcome = Literal["proceed", "skip", "defer"]

_OUTCOMES: frozenset[str] = frozenset({"proceed", "skip", "defer"})


def _parsed_body(body: str | None) -> Any:
    """Corps décodé, ou `None` s'il n'est pas du JSON exploitable.

    Un corps illisible est un cas NORMAL, pas une panne : la cible peut répondre
    du HTML sur une erreur. On rend `None`, la règle ne matchera pas, et le
    `default` tranchera — plutôt que de transformer une réponse inattendue en
    échec de l'automate.
    """
    if not body:
        return None
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return None


def _at_path(parsed: Any, path: str) -> Any:
    """Valeur au chemin pointé (`a.b.c`), ou `None` si le chemin n'aboutit pas.

    Volontairement limité à la traversée de dictionnaires : pas d'index de
    liste, pas de jokers. C'est ce qui garde la condition déclarative — dès
    qu'on ajoute une sélection, on a écrit un langage.
    """
    current = parsed
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def _matches(rule: dict[str, Any], status: int, parsed: Any) -> bool:
    """Tous les critères DÉCLARÉS par la règle doivent être satisfaits (ET).

    Une règle sans critère matche tout : c'est un `default` écrit en première
    position, et c'est assumé.
    """
    codes = rule.get("status")
    if codes is not None and status not in codes:
        return False
    path = rule.get("path")
    if path is not None:
        value = _at_path(parsed, str(path))
        # Comparaison en texte : le corps rend des types JSON, la condition est
        # saisie comme une chaîne. Comparer `1` et `"1"` comme égaux est le
        # comportement attendu de quelqu'un qui remplit un formulaire.
        if value is None or str(value) != str(rule.get("equals")):
            return False
    return True


def _as_outcome(value: Any, field: str) -> Outcome:
    """Valide une issue déclarée. Refuse plutôt que d'inventer une intention."""
    if value == "proceed":
        return "proceed"
    if value == "skip":
        return "skip"
    if value == "defer":
        return "defer"
    raise ValueError(
        f"pré-condition : '{field}' invalide ({value!r}) ; attendu " + ", ".join(sorted(_OUTCOMES))
    )


def evaluate(spec: dict[str, Any], *, status: int, body: str | None) -> Outcome:
    """Issue de la pré-condition pour une réponse donnée.

    Première règle qui matche l'emporte ; aucune ne matche → `default`.

    `default` est OBLIGATOIRE : un `proceed` tacite enverrait précisément
    l'appel qu'on cherchait à conditionner. On échoue à la configuration plutôt
    que d'inventer une intention.
    """
    default = _as_outcome(spec.get("default"), "default")
    parsed = _parsed_body(body)
    for rule in spec.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        if _matches(rule, status, parsed):
            return _as_outcome(rule.get("then"), "then")
    return default
