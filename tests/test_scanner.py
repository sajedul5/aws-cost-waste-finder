import boto3
import pytest
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    ReadTimeoutError,
)
from moto import mock_aws

from cost_waste_finder import scanner
from cost_waste_finder.config import Thresholds
from cost_waste_finder.models import Finding
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
    err = capsys.readouterr().err
    assert "Scanned ap-southeast-1" in err
    assert "Scanned ap-southeast-2" in err


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


@mock_aws
def test_scan_regions_keeps_region_order(fixed_prices: None) -> None:
    session = boto3.Session()
    regions = ["ap-southeast-2", "ap-southeast-1", "eu-west-1", "us-east-1"]
    for region in regions:
        session.client("ec2", region_name=region).create_volume(
            AvailabilityZone=f"{region}a", Size=10
        )

    findings = scanner.scan_regions(session, regions)

    assert [f.region for f in findings] == regions


@mock_aws
def test_parallel_scan_looks_up_each_price_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def counting_fetch(self, service, filters, usagetype):
        calls.append(filters["location"])
        return 0.10

    monkeypatch.setattr(PricingClient, "_fetch_price", counting_fetch)
    session = boto3.Session()
    regions = ["ap-southeast-1", "ap-southeast-2"]
    for region in regions:
        ec2 = session.client("ec2", region_name=region)
        for _ in range(3):
            ec2.create_volume(AvailabilityZone=f"{region}a", Size=10, VolumeType="gp3")

    scanner.scan_regions(session, regions)

    assert sorted(calls) == ["Asia Pacific (Singapore)", "Asia Pacific (Sydney)"]


def test_thread_safe_session_passes_through() -> None:
    session = boto3.Session(region_name="ap-southeast-1")
    shared = scanner.ThreadSafeSession(session)

    assert shared.region_name == "ap-southeast-1"
    assert shared.client("ec2").meta.region_name == "ap-southeast-1"


@mock_aws
def test_gp2_volume_on_stopped_instance_is_counted_once(fixed_prices: None) -> None:
    """Deleting the volume saves its full storage; converting it to gp3 first saves nothing more."""
    session = boto3.Session(region_name=REGION)
    ec2 = session.client("ec2")
    image_id = ec2.describe_images()["Images"][0]["ImageId"]
    stopped = ec2.run_instances(ImageId=image_id, MinCount=1, MaxCount=1)["Instances"][0][
        "InstanceId"
    ]
    running = ec2.run_instances(ImageId=image_id, MinCount=1, MaxCount=1)["Instances"][0][
        "InstanceId"
    ]
    volumes = {}
    for name, instance_id in (("stopped", stopped), ("running", running)):
        volumes[name] = ec2.create_volume(
            AvailabilityZone=f"{REGION}a", Size=500, VolumeType="gp2"
        )["VolumeId"]
        ec2.attach_volume(VolumeId=volumes[name], InstanceId=instance_id, Device="/dev/sdf")
    ec2.stop_instances(InstanceIds=[stopped])
    thresholds = Thresholds(stopped_days=-1)  # moto's stop time is "now"

    findings = scanner.scan(session, REGION, thresholds)

    gp2 = {f.resource_id for f in findings if f.check == "gp2-to-gp3"}
    assert volumes["stopped"] not in gp2  # already in the stopped-ec2 storage cost
    assert volumes["running"] in gp2
    assert [f.resource_id for f in findings if f.check == "stopped-ec2"] == [stopped]


def test_remove_overlaps_keeps_unrelated_findings() -> None:
    def finding(check: str, resource_id: str, **details) -> Finding:
        return Finding(check, resource_id, REGION, "test", details)

    findings = [
        finding("gp2-to-gp3", "vol-1"),
        finding("gp2-to-gp3", "vol-2"),
        finding("stopped-ec2", "i-1", volumes=[{"volume_id": "vol-1"}]),
        finding("unattached-ebs", "vol-1"),
    ]

    kept = [(f.check, f.resource_id) for f in scanner.remove_overlaps(findings)]

    assert kept == [
        ("gp2-to-gp3", "vol-2"),
        ("stopped-ec2", "i-1"),
        ("unattached-ebs", "vol-1"),
    ]


@mock_aws
def test_network_error_skips_only_that_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, fixed_prices: None
) -> None:
    def unreachable(session, region, thresholds):
        raise EndpointConnectionError(endpoint_url="https://ec2.example.invalid")

    unreachable.__module__ = "cost_waste_finder.checks.unreachable_check"
    session = boto3.Session(region_name=REGION)
    session.client("ec2").create_volume(AvailabilityZone=f"{REGION}a", Size=10)
    monkeypatch.setattr(scanner, "CHECKS", [unreachable, *scanner.CHECKS])

    findings = scanner.scan(session, REGION)

    assert len(findings) == 1
    assert "check unreachable_check skipped in ap-southeast-1: EndpointConnectionError" in (
        capsys.readouterr().err
    )


@mock_aws
def test_one_failing_region_keeps_the_others(
    monkeypatch: pytest.MonkeyPatch, fixed_prices: None
) -> None:
    def flaky(session, region, thresholds):
        if region == "ap-southeast-2":
            raise ReadTimeoutError(endpoint_url="https://ec2.ap-southeast-2.amazonaws.com")
        return []

    session = boto3.Session()
    for region in ("ap-southeast-1", "ap-southeast-2"):
        session.client("ec2", region_name=region).create_volume(
            AvailabilityZone=f"{region}a", Size=10
        )
    monkeypatch.setattr(scanner, "CHECKS", [flaky, *scanner.CHECKS])

    findings = scanner.scan_regions(session, ["ap-southeast-1", "ap-southeast-2"])

    assert sorted(f.region for f in findings) == ["ap-southeast-1", "ap-southeast-2"]


def test_credentials_error_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """No credentials must stop the scan, not print a "$0" report."""

    def no_credentials(session, region, thresholds):
        raise NoCredentialsError()

    monkeypatch.setattr(scanner, "CHECKS", [no_credentials])

    with pytest.raises(NoCredentialsError):
        scanner.scan(boto3.Session(region_name=REGION), REGION, pricing=object())
