import pytest
from click.testing import CliRunner

from cost_waste_finder import __version__
from cost_waste_finder.cli import cli


def test_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.output


def test_version() -> None:
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_scan_uses_region_option() -> None:
    result = CliRunner().invoke(cli, ["scan", "--region", "ap-southeast-1"])
    assert result.exit_code == 0
    assert "ap-southeast-1" in result.output


def test_scan_falls_back_to_config_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-2")
    result = CliRunner().invoke(cli, ["scan"])
    assert result.exit_code == 0
    assert "ap-southeast-2" in result.output


def test_scan_without_region_fails_clearly() -> None:
    result = CliRunner().invoke(cli, ["scan"])
    assert result.exit_code != 0
    assert "No region set" in result.output
