from __future__ import annotations

import json
import re

# Un placeholder = « { » suivi d'un identifiant nu (éventuellement pointé, ex.
# event.blockSlug) puis « } ». Les accolades JSON de structure ({"clé": …}, {})
# ne matchent pas : après « { » vient un guillemet, une espace ou « } », pas un
# identifiant. On ne détecte donc jamais une accolade de structure comme variable.
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][\w.]*)\}")


def unresolved_variables(template: str, variables: dict[str, str]) -> list[str]:
    """Placeholders du GABARIT sans variable correspondante, triés et dédupliqués.

    Détecté sur le gabarit, JAMAIS sur le rendu : une valeur substituée (contenu
    markdown d'un document) peut légitimement contenir des accolades — ce ne sont
    pas des placeholders. Une variable non résolue ne doit jamais partir en
    silence (cf. bug « gabarit non substitué à l'indexation ragflow »)."""
    keys = {m.group(1) for m in _PLACEHOLDER.finditer(template)}
    return sorted(k for k in keys if k not in variables)


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
