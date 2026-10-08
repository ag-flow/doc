"""Évaluation d'une pré-condition d'automate (ticket 74730995).

La condition est de la DONNÉE, pas un langage : une liste de règles ordonnées,
chacune testant le code HTTP et/ou une valeur du corps par égalité. Première
règle qui matche l'emporte ; aucune ne matche → `default`, qui est obligatoire.

Ce choix vient de la ligne du projet (« registre plutôt que condition ») : pas
de grammaire à spécifier, à valider ni à outiller dans l'écran, et le jeu reste
élargissable sans rien casser.

Trois issues, et elles ne sont pas interchangeables :
  - `proceed` : faire l'appel principal ;
  - `skip`    : ne pas l'appeler, et considérer l'event traité ;
  - `defer`   : ne pas l'appeler, et REVENIR plus tard (ni consommé, ni échoué).

Les deux cas réels du 2026-10-08 :
  - créer le workspace RAG → 404 = proceed, sinon skip (évite le 409) ;
  - indexer un document    → 200 = proceed, sinon defer (évite le dead-letter).
"""

from __future__ import annotations

import pytest

from docflow.automations.precheck import evaluate


def _spec(rules: list[dict], default: str) -> dict:
    return {"url": "https://x/check", "method": "GET", "rules": rules, "default": default}


# ── Les deux cas réels ────────────────────────────────────────────────────────


def test_creation_appelle_quand_la_ressource_est_absente() -> None:
    spec = _spec([{"status": [404], "then": "proceed"}], default="skip")

    assert evaluate(spec, status=404, body='{"detail":"not found"}') == "proceed"


def test_creation_s_abstient_quand_la_ressource_existe() -> None:
    """Le 409 observé en production ne doit plus jamais partir."""
    spec = _spec([{"status": [404], "then": "proceed"}], default="skip")

    assert evaluate(spec, status=200, body='{"slug":"test1-docs"}') == "skip"


def test_indexation_differe_quand_le_corpus_manque() -> None:
    """Différer, et non échouer : c'est ce qui évite le dead-letter."""
    spec = _spec([{"status": [200], "then": "proceed"}], default="defer")

    assert evaluate(spec, status=404, body="") == "defer"


# ── Condition sur le corps ────────────────────────────────────────────────────


def test_une_regle_peut_tester_une_valeur_du_corps() -> None:
    spec = _spec(
        [{"status": [200], "path": "state", "equals": "ready", "then": "proceed"}],
        default="defer",
    )

    assert evaluate(spec, status=200, body='{"state":"ready"}') == "proceed"
    assert evaluate(spec, status=200, body='{"state":"indexing"}') == "defer"


def test_le_chemin_peut_etre_imbrique() -> None:
    spec = _spec(
        [{"path": "workspace.state", "equals": "ready", "then": "proceed"}], default="defer"
    )

    assert evaluate(spec, status=200, body='{"workspace":{"state":"ready"}}') == "proceed"


def test_un_corps_illisible_ne_fait_pas_matcher_et_ne_leve_pas() -> None:
    """Un corps non-JSON est un cas NORMAL : la règle ne matche pas, c'est tout.

    Lever ici transformerait une réponse inattendue de la cible en panne de
    l'automate — exactement le genre d'échec qu'on vient de passer la journée
    à démêler.
    """
    spec = _spec([{"path": "state", "equals": "ready", "then": "proceed"}], default="defer")

    assert evaluate(spec, status=200, body="<html>oops</html>") == "defer"


def test_un_chemin_absent_ne_fait_pas_matcher() -> None:
    spec = _spec([{"path": "state", "equals": "ready", "then": "proceed"}], default="skip")

    assert evaluate(spec, status=200, body='{"autre":"chose"}') == "skip"


# ── Ordre et exhaustivité ─────────────────────────────────────────────────────


def test_la_premiere_regle_qui_matche_l_emporte() -> None:
    spec = _spec(
        [
            {"status": [200], "then": "skip"},
            {"status": [200], "then": "proceed"},
        ],
        default="defer",
    )

    assert evaluate(spec, status=200, body="{}") == "skip"


def test_les_criteres_d_une_regle_se_combinent_en_et() -> None:
    """Statut ET corps : une règle qui déclare les deux exige les deux."""
    spec = _spec(
        [{"status": [200], "path": "state", "equals": "ready", "then": "proceed"}],
        default="skip",
    )

    assert evaluate(spec, status=200, body='{"state":"ready"}') == "proceed"
    # Bon corps, mauvais statut → la règle ne matche pas.
    assert evaluate(spec, status=202, body='{"state":"ready"}') == "skip"


def test_aucune_regle_ne_matche_rend_le_defaut() -> None:
    spec = _spec([{"status": [404], "then": "proceed"}], default="defer")

    assert evaluate(spec, status=500, body="") == "defer"


def test_un_defaut_absent_est_refuse() -> None:
    """Pas de défaut implicite : un `proceed` tacite enverrait l'appel qu'on
    cherchait précisément à conditionner."""
    with pytest.raises(ValueError):
        evaluate({"url": "x", "method": "GET", "rules": []}, status=200, body="{}")
