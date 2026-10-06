import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from cost_waste_finder import scanner
from cost_waste_finder.pricing import PricingClient

REGION = "ap-southeast-1"


@mock_aws
def test_scan_finds_and_prices(fixed_prices: None) -> None:
    session = boto3.Session(region_name=REGION)
    session.client("ec2").create_volume(AvailabilityZone=f"{REGION}a", Size=50)

    findings = scanner.scan(session, REGION)

    assert len(findings) == 1
    assert findings[0].monthly_cost == 5.0


@mock_aws
def test_failing_check_is_skipped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, fixed_prices: None
) -> None:
    def denied(session, region, thresholds):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "DescribeX")

    denied.__module__ = "cost_waste_finder.checks.denied_check"
    session = boto3.Session(region_name=REGION)
    session.client("ec2").create_volume(AvailabilityZone=f"{REGION}a", Size=10)
    monkeypatch.setattr(scanner, "CHECKS", [denied, *scanner.CHECKS])

    findings = scanner.scan(session, REGION)

    assert len(findings) == 1  # the EBS check still ran
    assert "check denied_check skipped in ap-southeast-1: AccessDenied" in capsys.readouterr().err


@mock_aws
def test_pricing_failure_leaves_costs_unknown(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    def denied(self, service, filters, usagetype=None):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "GetProducts")

    monkeypatch.setattr(PricingClient, "get_price", denied)
    session = boto3.Session(region_name=REGION)
    session.client("ec2").create_volume(AvailabilityZone=f"{REGION}a", Size=10)

    findings = scanner.scan(session, REGION)

    assert findings[0].monthly_cost is None
    assert "pricing unavailable" in capsys.readouterr().err


@mock_aws
def test_enabled_regions() -> None:
    regions = scanner.enabled_regions(boto3.Session(), "us-east-1")

    assert "ap-southeast-1" in regions
    assert "ap-southeast-2" in regions
    assert regions == sorted(regions)


@mock_aws
def test_scan_regions_covers_each_region(fixed_prices: None, capsys: pytest.CaptureFixture) -> None:
    session = boto3.Session()
    for region in ("ap-southeast-1", "ap-southeast-2"):
        session.client("ec2", region_name=region).create_volume(
            AvailabilityZone=f"{region}a", Size=10
        )

    findings = scanner.scan_regions(session, ["ap-southeast-1", "ap-southeast-2"])

    assert sorted(f.region for f in findings) == ["ap-southeast-1", "ap-southeast-2"]
    assert "Scanning ap-southeast-2 (2/2)..." in capsys.readouterr().err


@mock_aws
def test_scan_regions_shares_one_price_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def counting_fetch(self, service, filters, usagetype):
        calls.append(filters["location"])
        return 0.10

    monkeypatch.setattr(PricingClient, "_fetch_price", counting_fetch)
    session = boto3.Session()
    ec2 = session.client("ec2", region_name=REGION)
    for _ in range(3):
        ec2.create_volume(AvailabilityZone=f"{REGION}a", Size=10, VolumeType="gp3")

    scanner.scan_regions(session, [REGION])

    assert calls == ["Asia Pacific (Singapore)"]  # 3 volumes, 1 price lookup
