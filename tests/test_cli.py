import boto3
import pytest
from click.testing import CliRunner
from moto import mock_aws

from cost_waste_finder import __version__
from cost_waste_finder.cli import cli

REGION = "ap-southeast-1"


def test_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.output


def test_version() -> None:
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


@mock_aws
def test_scan_prints_report(fixed_prices: None) -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    volume_id = ec2.create_volume(AvailabilityZone=f"{REGION}a", Size=100)["VolumeId"]

    result = CliRunner().invoke(cli, ["scan", "--region", REGION])

    assert result.exit_code == 0, result.output
    assert "Region: ap-southeast-1" in result.stdout
    assert "**You can save ~$10.00/month** (1 finding)" in result.stdout
    assert volume_id in result.stdout


@mock_aws
def test_scan_with_no_waste(fixed_prices: None) -> None:
    result = CliRunner().invoke(cli, ["scan", "--region", REGION])
    assert result.exit_code == 0
    assert "No waste found." in result.stdout


@mock_aws
def test_scan_falls_back_to_config_default(
    monkeypatch: pytest.MonkeyPatch, fixed_prices: None
) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-2")
    result = CliRunner().invoke(cli, ["scan"])
    assert result.exit_code == 0
    assert "Region: ap-southeast-2" in result.stdout


def test_scan_without_region_fails_clearly() -> None:
    result = CliRunner().invoke(cli, ["scan"])
    assert result.exit_code != 0
    assert "No region set" in result.output


def test_scan_with_bad_profile_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_PROFILE", "does-not-exist")
    result = CliRunner().invoke(cli, ["scan", "--region", REGION])
    assert result.exit_code != 0
    assert "AWS credentials problem" in result.output
    assert "Traceback" not in result.output
