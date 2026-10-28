"""Tests for the public MPASWF command-line presentation contract."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import mpaswf.cli as cli


def _report(*, valid: bool) -> dict[str, object]:
    return {
        "config": "/tmp/config.yaml",
        "workflow_contract_path": None,
        "valid": valid,
        "checks": [
            {
                "name": "software.monan_jedi_root",
                "path": "/runtime/monan-jedi",
                "expectation": "directory",
                "status": "OK",
                "ok": True,
                "detail": "",
            },
            {
                "name": "reference.forecast_streams",
                "path": "/runtime/streams.atmosphere_240km",
                "expectation": "file",
                "status": "MISSING" if not valid else "OK",
                "ok": valid,
                "detail": "",
            },
        ],
    }


def test_check_config_json_is_machine_readable(monkeypatch, capsys) -> None:
    """--json emits JSON only, with no human status prefix."""
    config = SimpleNamespace(path=Path("/tmp/config.yaml"))
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "config_preflight_report", lambda loaded: _report(valid=True))

    result = cli.main(["check-config", "--config", "/tmp/config.yaml", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert result == 0
    assert payload["valid"] is True
    assert "MPASWF config preflight" not in captured.out


def test_check_config_human_output_uses_standard_ui(monkeypatch, capsys) -> None:
    """Human output uses MPASWF status markers and a concise final summary."""
    config = SimpleNamespace(path=Path("/tmp/config.yaml"))
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "config_preflight_report", lambda loaded: _report(valid=False))
    monkeypatch.setenv("MPASWF_COLOR", "never")

    result = cli.main(["check-config", "--config", "/tmp/config.yaml"])

    captured = capsys.readouterr().out
    assert result == 1
    assert "• MPASWF config preflight: /tmp/config.yaml." in captured
    assert "✓ software.monan_jedi_root — OK" in captured
    assert "✗ reference.forecast_streams — MISSING" in captured
    assert "✗ MPASWF config preflight: failed — 1 of 2 checks failed." in captured


def test_check_config_invalid_yaml_returns_clean_error(monkeypatch, capsys) -> None:
    from mpaswf.config import ConfigurationError

    def invalid(_path):
        raise ConfigurationError("Missing required key: runtime.config_dt")

    monkeypatch.setattr(cli, "load_config", invalid)
    assert cli.main(["check-config", "--config", "/tmp/invalid.yaml"]) == 1
    captured = capsys.readouterr()
    assert "runtime.config_dt" in captured.err
    assert "How to fix" in captured.err
    assert "Traceback" not in captured.err


def test_check_config_invalid_yaml_json_remains_parseable(monkeypatch, capsys) -> None:
    from mpaswf.config import ConfigurationError

    def invalid(_path):
        raise ConfigurationError("Missing YAML value")

    monkeypatch.setattr(cli, "load_config", invalid)
    assert cli.main(["check-config", "--config", "/tmp/invalid.yaml", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["valid"] is False
    assert data["error"]["status"] == "INVALID_CONFIGURATION"
    assert data["checks"] == []


def test_check_config_lists_failed_check_corrections(monkeypatch, capsys) -> None:
    config = SimpleNamespace(path=Path("/tmp/config.yaml"))
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "config_preflight_report", lambda loaded: _report(valid=False))
    monkeypatch.setenv("MPASWF_COLOR", "never")
    assert cli.main(["check-config", "--config", "/tmp/config.yaml"]) == 1
    out = capsys.readouterr().out
    assert "Required corrections:" in out
    assert "reference.forecast_streams:" in out
