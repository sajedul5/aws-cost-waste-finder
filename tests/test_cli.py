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


def test_scan_help_lists_threshold_options() -> None:
    result = CliRunner().invoke(cli, ["scan", "--help"])
    for option in (
        "--lookback-days",
        "--cpu-threshold",
        "--network-threshold-mb",
        "--nat-threshold-gb",
        "--lb-requests-threshold",
        "--snapshot-age-days",
    ):
        assert option in result.output


def test_scan_passes_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def fake_scan(session, regions, thresholds):
        seen["thresholds"] = thresholds
        return []

    monkeypatch.setattr("cost_waste_finder.cli.scan_regions", fake_scan)
    args = ["scan", "--region", REGION, "--cpu-threshold", "10", "--lookback-days", "7"]
    result = CliRunner().invoke(cli, args)

    assert result.exit_code == 0, result.output
    assert seen["thresholds"].cpu_percent == 10
    assert seen["thresholds"].lookback_days == 7
    assert seen["thresholds"].snapshot_age_days == 90  # default kept


def test_scan_rejects_zero_lookback() -> None:
    result = CliRunner().invoke(cli, ["scan", "--region", REGION, "--lookback-days", "0"])
    assert result.exit_code != 0


@mock_aws
def test_scan_all_regions(monkeypatch: pytest.MonkeyPatch, fixed_prices: None) -> None:
    regions = ["ap-southeast-1", "ap-southeast-2"]
    monkeypatch.setattr(
        "cost_waste_finder.cli.enabled_regions", lambda session, any_region: regions
    )
    boto3.client("ec2", region_name="ap-southeast-2").create_volume(
        AvailabilityZone="ap-southeast-2a", Size=100
    )

    result = CliRunner().invoke(cli, ["scan", "--all-regions"])

    assert result.exit_code == 0, result.output
    assert "Regions (2): ap-southeast-1, ap-southeast-2" in result.stdout
    assert "| ap-southeast-2 |" in result.stdout


def test_scan_rejects_region_with_all_regions() -> None:
    result = CliRunner().invoke(cli, ["scan", "--region", REGION, "--all-regions"])
    assert result.exit_code != 0
    assert "either --region or --all-regions" in result.output
