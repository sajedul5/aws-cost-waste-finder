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
    def denied(session, region):
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
    def denied(self, service, filters, usagetype_suffix=None):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "GetProducts")

    monkeypatch.setattr(PricingClient, "get_price", denied)
    session = boto3.Session(region_name=REGION)
    session.client("ec2").create_volume(AvailabilityZone=f"{REGION}a", Size=10)

    findings = scanner.scan(session, REGION)

    assert findings[0].monthly_cost is None
    assert "pricing unavailable" in capsys.readouterr().err
