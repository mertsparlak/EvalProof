from __future__ import annotations

import importlib.metadata
import json
import tomllib
from pathlib import Path

import pytest

from evalproof import __version__
from evalproof.cli import main


@pytest.mark.parametrize("args", [["--help"], ["scan", "--help"], ["rules", "--help"]])
def test_cli_help_exits_successfully(args, capsys):
    assert main(args) == 0
    assert "usage:" in capsys.readouterr().out


def test_runtime_and_distribution_versions_are_aligned():
    assert __version__ == "0.2.2"
    assert importlib.metadata.version("evalproof") == "0.2.2"


def test_json_report_uses_runtime_package_version(tmp_path):
    (tmp_path / "eval.jsonl").write_text('{"prompt":"release smoke"}\n', encoding="utf-8")
    output = tmp_path / "report.json"

    result = main(["scan", str(tmp_path), "--json", "--output", str(output)])

    assert result == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == "1.0"
    assert report["tool"] == {"name": "evalproof", "version": "0.2.2"}


def test_package_metadata_declares_expected_release_version():
    project = Path(__file__).parents[1] / "pyproject.toml"
    assert 'version = "0.2.2"' in project.read_text(encoding="utf-8")


def test_package_discovery_is_limited_to_evalproof():
    project = Path(__file__).parents[1] / "pyproject.toml"
    metadata = tomllib.loads(project.read_text(encoding="utf-8"))
    assert metadata["tool"]["setuptools"]["packages"]["find"]["include"] == ["evalproof", "evalproof.*"]
