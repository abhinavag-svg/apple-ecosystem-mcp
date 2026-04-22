from __future__ import annotations

import runpy
import sys
from unittest.mock import Mock

import pytest


def test_module_version_prints_and_exits(monkeypatch, capsys, mock_package_version):
    mock_package_version("0.1.0")
    monkeypatch.setattr(sys, "argv", ["apple-ecosystem-mcp", "--version"])
    with pytest.raises(SystemExit) as e:
        runpy.run_module("apple_ecosystem_mcp", run_name="__main__")
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == "0.1.0"


def test_main_calls_permissions_then_server_run(monkeypatch):
    check_mock = Mock()
    run_mock = Mock()
    monkeypatch.setattr("apple_ecosystem_mcp.main.check_permissions", check_mock)
    monkeypatch.setattr("apple_ecosystem_mcp.main.run", run_mock)
    monkeypatch.setattr(sys, "argv", ["apple-ecosystem-mcp"])

    from apple_ecosystem_mcp.main import main

    main()
    check_mock.assert_called_once()
    run_mock.assert_called_once()


def test_main_does_not_start_server_when_version_flag(monkeypatch, mock_package_version):
    from apple_ecosystem_mcp import server

    mock_package_version("0.1.0")
    run_mock = Mock()
    monkeypatch.setattr(server, "run", run_mock)
    monkeypatch.setattr(sys, "argv", ["apple-ecosystem-mcp", "--version"])

    from apple_ecosystem_mcp.main import main

    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    run_mock.assert_not_called()
