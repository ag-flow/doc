"""`scripts/declarer-exposition.sh` — déclarer un service au portail depuis l'infra.

Ce qui se joue, et qui ne se voit pas en lisant le script : le `PORTAL_TOKEN`
ne doit JAMAIS passer en argv (`ps auxww` est lisible par tout processus local),
et un portail injoignable ne doit pas faire échouer le déploiement qui appelle
ce script. On l'exerce donc pour de vrai, avec un faux `curl` qui enregistre ce
qu'il a reçu.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "declarer-exposition.sh"

FAUX_CURL = """#!/usr/bin/env bash
# Faux curl : consigne argv et stdin, puis rend le code HTTP demande.
printf '%s\\n' "$@" > "$TRACE_DIR/argv"
cat > "$TRACE_DIR/stdin"
printf '%s' "${FAUX_CODE:-200}"
exit 0
"""


def _lancer(
    tmp_path: Path, extra: list[str] | None = None, **env: str
) -> subprocess.CompletedProcess[str]:
    faux = tmp_path / "bin"
    faux.mkdir(exist_ok=True)
    (faux / "curl").write_text(FAUX_CURL)
    (faux / "curl").chmod(0o755)
    trace = tmp_path / "trace"
    trace.mkdir(exist_ok=True)
    return subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--portal",
            "https://dev.yoops.org",
            "--workspace",
            "docflow",
            "--service",
            "docflow",
            "--target-host",
            "192.168.10.90",
            "--target-port",
            "8080",
            "--host",
            "test-doc-900",
            *(extra or []),
        ],
        env={
            **os.environ,
            "PATH": f"{faux}:{os.environ['PATH']}",
            "TRACE_DIR": str(trace),
            **env,
        },
        capture_output=True,
        text=True,
    )


def test_le_jeton_ne_passe_jamais_en_argv(tmp_path: Path) -> None:
    """L'argv de curl est lisible par tout processus local : le jeton descend
    par un fichier de config sur stdin (`-K -`), comme les autres scripts."""
    r = _lancer(tmp_path, PORTAL_TOKEN="jeton-secret")

    assert r.returncode == 0, r.stderr
    argv = (tmp_path / "trace" / "argv").read_text()
    assert "jeton-secret" not in argv
    assert "jeton-secret" in (tmp_path / "trace" / "stdin").read_text()


def test_la_declaration_porte_ce_qui_a_ete_demande(tmp_path: Path) -> None:
    r = _lancer(tmp_path, PORTAL_TOKEN="x")
    assert r.returncode == 0

    argv = (tmp_path / "trace" / "argv").read_text().splitlines()
    assert "https://dev.yoops.org/admin/expositions" in argv
    assert "PUT" in argv
    charge = json.loads(next(a for a in argv if a.lstrip().startswith("{")))
    assert charge == {
        "workspace": "docflow",
        "service": "docflow",
        "host": "test-doc-900",
        "target_host": "192.168.10.90",
        "target_port": 8080,
        "scheme": "http",
        "entry_path": "",
    }


def test_le_chemin_d_entree_part_dans_la_charge(tmp_path: Path) -> None:
    """`--path /vmui/` : le lien de l'annuaire doit ouvrir la page d'entrée du
    service, pas une racine vide."""
    r = _lancer(tmp_path, extra=["--path", "/vmui/"], PORTAL_TOKEN="x")
    assert r.returncode == 0
    argv = (tmp_path / "trace" / "argv").read_text().splitlines()
    charge = json.loads(next(a for a in argv if a.lstrip().startswith("{")))
    assert charge["entry_path"] == "/vmui/"


def test_defaut_vise_l_endpoint_admin(tmp_path: Path) -> None:
    """Sans `--me` : voie d'infra admin, endpoint /admin/expositions."""
    r = _lancer(tmp_path, PORTAL_TOKEN="x")
    assert r.returncode == 0
    argv = (tmp_path / "trace" / "argv").read_text().splitlines()
    assert "https://dev.yoops.org/admin/expositions" in argv


def test_me_vise_l_endpoint_proprietaire(tmp_path: Path) -> None:
    """Avec `--me` : voie de l'agent (TOTP), endpoint /me/expositions — le
    service est déclaré sous le workspace de l'appelant authentifié."""
    r = _lancer(tmp_path, extra=["--me"], PORTAL_TOKEN="docflow:12345678")
    assert r.returncode == 0
    argv = (tmp_path / "trace" / "argv").read_text().splitlines()
    assert "https://dev.yoops.org/me/expositions" in argv
    assert "https://dev.yoops.org/admin/expositions" not in argv
    # Le credential TOTP descend toujours par stdin, jamais en argv.
    assert "docflow:12345678" not in "\n".join(argv)
    assert "docflow:12345678" in (tmp_path / "trace" / "stdin").read_text()


def test_sans_jeton_on_passe_son_chemin_sans_bruit(tmp_path: Path) -> None:
    """Une stack déployée hors contexte portail ne doit pas voir d'erreur."""
    r = _lancer(tmp_path)

    assert r.returncode == 0
    assert not (tmp_path / "trace" / "argv").exists(), "curl n'aurait pas dû être appelé"


def test_un_portail_injoignable_ne_fait_pas_echouer_le_deploiement(tmp_path: Path) -> None:
    """Best-effort : la déclaration se rejoue au prochain déploiement."""
    r = _lancer(tmp_path, PORTAL_TOKEN="x", FAUX_CODE="503")

    assert r.returncode == 0
    assert "503" in r.stderr or "AVERTISSEMENT" in r.stderr
