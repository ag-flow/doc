from __future__ import annotations

import json


def render_body(template: str, variables: dict[str, str]) -> str:
    """Substitue les variables dans un template JSON.

    Chaque valeur est encodée via json.dumps (sans guillemets externes) pour
    garantir l'échappement de " et \\n. L'utilisateur place les variables dans
    des positions de chaîne JSON déjà délimitées par des guillemets.
    """
    out = template
    for key, value in variables.items():
        encoded = json.dumps(value)[1:-1]
        out = out.replace("{" + key + "}", encoded)
    return out


def render_and_validate(template: str, variables: dict[str, str]) -> str | None:
    """Substitue puis valide que le résultat est du JSON bien formé.

    Retourne la chaîne JSON rendue, ou None si la substitution produit un
    JSON invalide (status 'failed' à l'appelant, pas d'appel HTTP émis).
    """
    rendered = render_body(template, variables)
    try:
        json.loads(rendered)
        return rendered
    except json.JSONDecodeError:
        return None
