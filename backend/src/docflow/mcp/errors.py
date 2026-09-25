"""Codification des erreurs de la surface MCP.

Jusqu'ici un échec d'outil repartait au client sous trois formes différentes :
une phrase française libre (la majorité), un objet `{code, message}`
(`update_document`), un objet enrichi (validation de contenu). Un client ne
pouvait donc distinguer « document introuvable » de « droits refusés » qu'en
analysant du texte — c'est-à-dire en pariant sur une formulation.

Forme unique, arrêtée le 2026-09-25 :

    {"error": "<phrase lisible>",          # inchangé : rétro-compatible
     "error_code": "<code machine>",       # sur quoi le client branche
     "error_detail": {...}}                # seulement s'il y a plus à dire

`error` reste une chaîne : les clients déjà écrits continuent de fonctionner.
`error_code` est ce qui doit être testé. `error_detail` porte ce qui permet de
réagir sans relire (état courant d'un conflit, liste d'anomalies de validation).
"""

from __future__ import annotations

from typing import Any

# ── Taxonomie ────────────────────────────────────────────────────────────────
#
# Volontairement courte. Un code n'existe que si un client peut en faire
# QUELQUE CHOSE de différent : re-résoudre un identifiant, recharger un état,
# corriger un argument, abandonner. Multiplier les codes sans changer la
# réaction attendue ne fait que déplacer l'ambiguïté du texte vers le code.

#: Argument mal formé ou absent — la correction appartient à l'appelant.
INVALID = "invalid"
#: Ressource inexistante, ou hors du workspace indiqué.
NOT_FOUND = "not_found"
#: Droits insuffisants : périmètre de clé API, accès workspace, outil admin.
FORBIDDEN = "forbidden"
#: État incompatible avec l'opération (dépendances, unicité, cycle…).
CONFLICT = "conflict"
#: `expected_version` périmée. `error_detail` porte l'état COURANT.
VERSION_CONFLICT = "version_conflict"
#: `expected_version` requise et non fournie.
VERSION_REQUIRED = "version_required"
#: Révision demandée inexistante. `error_detail` porte les bornes disponibles.
VERSION_NOT_FOUND = "version_not_found"
#: Type fonctionnel obligatoire et non fourni.
FUNCTIONAL_TYPE_REQUIRED = "functional_type_required"
#: Contenu refusé par le codec de son type. `error_detail` porte les anomalies.
CONTENT_INVALID = "content_invalid"
#: Contenu même pas lisible (YAML cassé, JSON tronqué). Distinct de
#: `content_invalid` : là il n'y a rien à corriger ligne à ligne, il faut
#: reprendre la syntaxe. Codes posés par `documents.content_validation`.
CONTENT_UNPARSEABLE = "content_unparseable"
#: Nom d'outil inconnu du serveur.
UNKNOWN_TOOL = "unknown_tool"
#: Échec non prévu — un bug côté serveur, pas une faute de l'appelant.
INTERNAL = "internal"

#: Tous les codes émis. Sert au test qui interdit d'en inventer un hors liste :
#: un code non déclaré est un code que personne ne peut documenter.
ALL_CODES = frozenset(
    {
        INVALID,
        NOT_FOUND,
        FORBIDDEN,
        CONFLICT,
        VERSION_CONFLICT,
        VERSION_REQUIRED,
        VERSION_NOT_FOUND,
        FUNCTIONAL_TYPE_REQUIRED,
        CONTENT_INVALID,
        CONTENT_UNPARSEABLE,
        UNKNOWN_TOOL,
        INTERNAL,
    }
)

# Statut HTTP des services internes → code MCP. Le service lève déjà une
# HTTPException correctement qualifiée ; on la traduit plutôt que de redécider.
_BY_STATUS = {
    400: INVALID,
    401: FORBIDDEN,
    403: FORBIDDEN,
    404: NOT_FOUND,
    409: CONFLICT,
    422: INVALID,
}


# Phrase de repli quand le service n'a posé que des champs de contexte. Reste
# courte et actionnable : un message générique qui n'apprend rien vaut mieux
# qu'une repr de dictionnaire, mais ne remplace pas un message écrit à la main.
_DEFAULT_MESSAGE = {
    CONFLICT: "état courant incompatible avec l'opération demandée",
    NOT_FOUND: "ressource introuvable",
    FORBIDDEN: "opération refusée : droits insuffisants",
    INVALID: "arguments refusés",
}


def err(code: str, message: object, **detail: Any) -> dict[str, object]:
    """Construit une réponse d'erreur à la forme unique.

    `message` accepte autre chose qu'une chaîne parce que `HTTPException.detail`
    n'en est pas toujours une ; il est rendu tel quel en texte lisible.
    `error_detail` n'apparaît que s'il porte quelque chose — un objet vide
    inviterait le client à y chercher une information qui n'existe pas.
    """
    if code not in ALL_CODES:
        raise ValueError(f"code d'erreur MCP non déclaré : {code!r}")
    payload: dict[str, object] = {
        "error": message if isinstance(message, str) else str(message),
        "error_code": code,
    }
    if detail:
        payload["error_detail"] = detail
    return payload


def from_http(status_code: int, detail: object, **extra: Any) -> dict[str, object]:
    """Traduit une HTTPException d'un service interne en erreur MCP.

    Un statut inconnu tombe sur `invalid` plutôt que sur `internal` : les
    services ne lèvent des statuts hors table que pour des refus de validation,
    et qualifier à tort un refus d'appelant en bug serveur brouillerait la seule
    distinction qui compte pour l'exploitation.

    **Un `detail` déjà structuré fait autorité.** `documents.content_validation`
    qualifie lui-même son refus (`content_invalid` / `content_unparseable`) et
    joint les anomalies ligne à ligne ; le réduire au statut HTTP effacerait
    précisément ce qui permet à l'appelant de corriger en une passe.
    """
    if isinstance(detail, dict):
        raw_code = detail.get("code")
        code = (
            raw_code
            if isinstance(raw_code, str) and raw_code in ALL_CODES
            else _BY_STATUS.get(status_code, INVALID)
        )
        rest = {k: v for k, v in detail.items() if k not in ("code", "message")}
        # Un service peut ne poser QUE des champs de contexte (le conflit de
        # valeur de propriété rend {version, value, …}). Rendre le dict comme
        # message donnerait une repr Python à lire par un humain : on prend une
        # phrase par défaut et le dict part entier dans `error_detail`.
        message = detail.get("message") or _DEFAULT_MESSAGE.get(code, "opération refusée")
        return err(code, message, **rest, **extra)
    return err(_BY_STATUS.get(status_code, INVALID), detail, **extra)


def version_conflict(current: dict[str, object]) -> dict[str, object]:
    """Conflit d'`expected_version`, portant l'état courant.

    Le client réapplique ses modifications sur cet état et réécrit : sans ces
    champs il lui faudrait une relecture, donc un aller-retour de plus et une
    nouvelle fenêtre de conflit.
    """
    return err(
        VERSION_CONFLICT,
        "expected_version périmée : recharger l'état courant, réappliquer les "
        "modifications, réécrire avec la version courante.",
        version=current.get("version"),
        title=current.get("title"),
        contenu=current.get("content"),
    )


def is_error(payload: object) -> bool:
    """Vrai si ce payload est une réponse d'échec."""
    return isinstance(payload, dict) and bool(payload.get("error"))


def code_of(payload: object) -> str | None:
    """Code d'une réponse d'échec, ou None si ce n'en est pas une.

    Tolère une réponse d'erreur sans `error_code` : il en reste dans les
    modules non encore migrés, et un log qui échouerait sur ce cas serait pire
    que le trou qu'il vient combler.
    """
    if not is_error(payload):
        return None
    assert isinstance(payload, dict)
    code = payload.get("error_code")
    return code if isinstance(code, str) else "unqualified"
