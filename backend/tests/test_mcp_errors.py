"""Contrat d'erreur de la surface MCP et journal des appels.

Ce que ces tests protègent : un client doit pouvoir brancher sur `error_code`
sans jamais lire le texte français, et un appel qui échoue doit laisser une
trace. Le second point vient d'un constat d'exploitation : sur sept jours,
~1000 appels par bucket et **zéro** ligne d'erreur — parce que rien n'en
écrivait, pas parce que rien n'échouait.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import pytest
from mcp.types import CallToolResult, TextContent
from structlog.testing import capture_logs

from docflow.mcp import calllog, errors
from docflow.mcp.server import _finalize_tool_result, _payload_of, _text

# ── Forme de l'erreur ────────────────────────────────────────────────────────


def test_la_forme_porte_les_trois_champs_attendus() -> None:
    payload = errors.err(errors.NOT_FOUND, "document 'x' introuvable")
    # `error` reste une CHAÎNE : c'est ce qui laisse fonctionner les clients
    # écrits avant la codification.
    assert payload == {"error": "document 'x' introuvable", "error_code": "not_found"}


def test_error_detail_absent_quand_il_n_y_a_rien_a_dire() -> None:
    """Un objet vide inviterait le client à y chercher ce qui n'existe pas."""
    assert "error_detail" not in errors.err(errors.INVALID, "doc_id : UUID invalide")


def test_error_detail_porte_les_champs_supplementaires() -> None:
    payload = errors.err(errors.CONFLICT, "refusé", dependents=3, documents=1)
    assert payload["error_detail"] == {"dependents": 3, "documents": 1}


def test_un_code_non_declare_est_refuse() -> None:
    """Inventer un code en passant, c'est un code que personne ne documentera."""
    with pytest.raises(ValueError, match="non déclaré"):
        errors.err("oups_je_linvente", "message")


@pytest.mark.parametrize(
    ("status", "expected"),
    [(400, "invalid"), (403, "forbidden"), (404, "not_found"), (409, "conflict"), (422, "invalid")],
)
def test_traduction_des_statuts_de_service(status: int, expected: str) -> None:
    assert errors.from_http(status, "raison")["error_code"] == expected


def test_un_statut_inconnu_ne_devient_pas_un_bug_serveur() -> None:
    """`internal` doit rester le signal d'une panne, pas d'un refus d'appelant."""
    assert errors.from_http(418, "raison")["error_code"] == "invalid"


def test_un_detail_deja_qualifie_fait_autorite() -> None:
    """`content_validation` qualifie lui-même son refus et joint les anomalies.

    Le réduire au statut HTTP effacerait exactement ce qui permet de corriger
    en une passe au lieu d'un aller-retour par faute.
    """
    detail = {
        "code": "content_invalid",
        "message": "contenu invalide",
        "issues": [{"path": "fields[0].type", "code": "physical_type"}],
        "doc": "grammaire",
    }
    payload = errors.from_http(422, detail)
    assert payload["error_code"] == "content_invalid"
    assert payload["error"] == "contenu invalide"
    assert payload["error_detail"] == {"issues": detail["issues"], "doc": "grammaire"}


def test_un_detail_sans_message_ne_rend_pas_une_repr_python() -> None:
    """Le conflit de valeur de propriété ne pose que des champs de contexte."""
    payload = errors.from_http(409, {"version": 1, "value": "haute"})
    assert payload["error_code"] == "conflict"
    assert "{" not in str(payload["error"])  # une phrase, pas un dict stringifié
    assert payload["error_detail"] == {"version": 1, "value": "haute"}


def test_le_conflit_de_version_porte_l_etat_courant() -> None:
    """Sans ces champs, le client devrait relire — donc rouvrir une fenêtre de conflit."""
    payload = errors.version_conflict({"version": 7, "title": "T", "content": "C"})
    assert payload["error_code"] == "version_conflict"
    assert payload["error_detail"] == {"version": 7, "title": "T", "contenu": "C"}


def test_code_of_tolere_une_erreur_non_qualifiee() -> None:
    """Un log qui lèverait sur ce cas serait pire que le trou qu'il comble."""
    assert errors.code_of({"error": "ancienne forme"}) == "unqualified"
    assert errors.code_of({"ok": True}) is None


# ── isError : le statut doit refléter l'échec ────────────────────────────────


def test_une_erreur_codifiee_reste_marquee_is_error() -> None:
    """Sans ce marquage, la gateway répond ok:true / 200 pour un échec."""
    result = _finalize_tool_result(_text(errors.err(errors.NOT_FOUND, "introuvable")))
    assert isinstance(result, CallToolResult)
    assert result.isError is True


def test_un_succes_n_est_pas_marque() -> None:
    assert not isinstance(_finalize_tool_result(_text({"id": "abc"})), CallToolResult)


def test_payload_of_ignore_une_reponse_non_json() -> None:
    assert _payload_of([TextContent(type="text", text="pas du json")]) is None


# ── Journal des appels ───────────────────────────────────────────────────────


def _lines(cap: list[dict[str, Any]], event: str) -> list[dict[str, Any]]:
    return [line for line in cap if line.get("event") == event]


def test_un_appel_reussi_laisse_une_ligne() -> None:
    with capture_logs() as cap:
        with calllog.ToolCall("get_document", {"workspace_slug": "ws", "doc_id": "x"}) as call:
            call.record({"id": "x"})
    (line,) = _lines(cap, "mcp_tool_call_done")
    assert line["outcome"] == "ok"
    assert line["tool"] == "get_document"
    assert "code" not in line


def test_un_appel_en_echec_porte_son_code() -> None:
    with capture_logs() as cap:
        with calllog.ToolCall("update_document", {"doc_id": "x"}) as call:
            call.record(errors.err(errors.VERSION_CONFLICT, "périmée"))
    (line,) = _lines(cap, "mcp_tool_call_done")
    assert line["outcome"] == "error"
    assert line["code"] == "version_conflict"
    # `warning` et non `error` : un échec d'appelant ne doit pas rendre le
    # niveau `error` inexploitable en alerte.
    assert line["log_level"] == "warning"


def test_une_panne_serveur_reste_au_niveau_error() -> None:
    with capture_logs() as cap:
        with calllog.ToolCall("get_maquette_png", {}) as call:
            call.record(errors.err(errors.INTERNAL, "rendu indisponible"))
    (line,) = _lines(cap, "mcp_tool_call_done")
    assert line["log_level"] == "error"


def test_une_exception_est_journalisee_et_remonte() -> None:
    """Le journal ne doit pas avaler la panne qu'il observe."""
    with capture_logs() as cap:
        with pytest.raises(RuntimeError):
            with calllog.ToolCall("list_workspaces", {}):
                raise RuntimeError("boum")
    (line,) = _lines(cap, "mcp_tool_call_done")
    assert line["outcome"] == "exception"
    assert line["log_level"] == "error"


def test_le_journal_ne_sort_jamais_la_valeur_des_arguments() -> None:
    """Les arguments transportent du contenu utilisateur : seuls les NOMS sortent.

    Exception assumée : workspace_slug et block_slug, qui sont des identifiants
    publics — sans eux, « not_found » ne dit pas de quoi on parle.
    """
    secret = "mot de passe en clair dans le corps du document"
    with capture_logs() as cap:
        with calllog.ToolCall(
            "update_document",
            {"workspace_slug": "globals", "doc_id": "abc", "contenu": secret},
        ) as call:
            call.record(errors.err(errors.NOT_FOUND, "introuvable"))
    (line,) = _lines(cap, "mcp_tool_call_done")
    assert line["arg_keys"] == ["contenu", "doc_id", "workspace_slug"]
    assert line["workspace_slug"] == "globals"
    assert secret not in json.dumps(line, default=str)
    assert "abc" not in json.dumps(line, default=str)  # doc_id : nom seulement


def test_la_duree_est_mesuree() -> None:
    with capture_logs() as cap:
        with calllog.ToolCall("list_workspaces", {}) as call:
            call.record({"ok": True})
    (line,) = _lines(cap, "mcp_tool_call_done")
    assert isinstance(line["duration_ms"], float)
    assert line["duration_ms"] >= 0


# ── Câblage réel ─────────────────────────────────────────────────────────────
#
# Les tests ci-dessus valident `ToolCall` isolément. Un composant juste mais
# jamais appelé ne sert à rien : ceux-ci passent par le vrai point d'entrée.


async def test_le_journal_est_reellement_cable_sur_le_dispatch(db_pool: asyncpg.Pool) -> None:
    """Un appel qui échoue au dispatch laisse une ligne — sans mise en scène."""
    from docflow.mcp.server import _call_tool, configure

    configure(db_pool)
    with capture_logs() as cap:
        result = await _call_tool("outil_inexistant", {})

    (line,) = _lines(cap, "mcp_tool_call_done")
    assert line["outcome"] == "error"
    assert line["code"] == "unknown_tool"
    assert line["tool"] == "outil_inexistant"
    # Et le client, lui, reçoit bien un échec marqué.
    assert isinstance(result, CallToolResult) and result.isError is True


async def test_un_appel_nominal_est_journalise_lui_aussi(db_pool: asyncpg.Pool) -> None:
    """« Log sur TOUS les appels » : le succès compte autant que l'échec —
    sans lui, on ne sait pas distinguer « aucune erreur » de « aucun trafic »."""
    from docflow.mcp.server import _call_tool, configure

    configure(db_pool)
    with capture_logs() as cap:
        await _call_tool("list_workspaces", {})

    (line,) = _lines(cap, "mcp_tool_call_done")
    assert line["outcome"] == "ok"
    assert line["tool"] == "list_workspaces"
