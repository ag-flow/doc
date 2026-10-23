"""Vérifie que le SDK harpocrate expose le module `connect` (apporté par la 0.8.0).

Fondation du chantier « Connecter à Harpocrate » (feature b95ed9f4) : la suite
a besoin de `harpocrate.connect.{start,finish,ConnectState,ConnectResult}` et
de `harpocrate.exceptions.ConnectError`, absents en 0.6.0.
"""

from __future__ import annotations


def test_harpocrate_connect_module_exposes_start_and_finish() -> None:
    import harpocrate.connect as connect

    assert hasattr(connect, "start")
    assert hasattr(connect, "finish")
    assert hasattr(connect, "ConnectState")
    assert hasattr(connect, "ConnectResult")


def test_harpocrate_exceptions_exposes_connect_error() -> None:
    from harpocrate.exceptions import ConnectError

    assert issubclass(ConnectError, Exception)
