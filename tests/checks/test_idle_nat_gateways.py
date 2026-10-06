import boto3
from helpers import GB, REGION, days_later, put_daily
from moto import mock_aws

from cost_waste_finder.checks import CHECKS, idle_nat_gateways
from cost_waste_finder.config import Thresholds

LATER = days_later(15)


def create_nat(session: boto3.Session, gb_per_day: float | None) -> str:
    ec2 = session.client("ec2")
    subnet_id = ec2.describe_subnets()["Subnets"][0]["SubnetId"]
    allocation_id = ec2.allocate_address(Domain="vpc")["AllocationId"]
    nat_id = ec2.create_nat_gateway(SubnetId=subnet_id, AllocationId=allocation_id)["NatGateway"][
        "NatGatewayId"
    ]
    if gb_per_day is not None:
        cloudwatch = session.client("cloudwatch")
        dims = {"NatGatewayId": nat_id}
        for metric in ("BytesOutToDestination", "BytesOutToSource"):
            put_daily(cloudwatch, "AWS/NATGateway", metric, dims, gb_per_day / 2 * GB, LATER)
    return nat_id


@mock_aws
def test_finds_idle_nat_gateway() -> None:
    session = boto3.Session(region_name=REGION)
    nat_id = create_nat(session, gb_per_day=0.001)

    findings = idle_nat_gateways.check(session, REGION, Thresholds(), now=LATER)

    assert [f.resource_id for f in findings] == [nat_id]
    assert findings[0].check == "idle-nat-gateway"
    assert "sent 0.01 GB in 14 days" in findings[0].reason


@mock_aws
def test_nat_without_any_traffic_is_idle() -> None:
    session = boto3.Session(region_name=REGION)
    nat_id = create_nat(session, gb_per_day=None)

    findings = idle_nat_gateways.check(session, REGION, Thresholds(), now=LATER)

    assert [f.resource_id for f in findings] == [nat_id]


@mock_aws
def test_busy_nat_gateway_is_not_idle() -> None:
    session = boto3.Session(region_name=REGION)
    create_nat(session, gb_per_day=5)

    assert idle_nat_gateways.check(session, REGION, Thresholds(), now=LATER) == []


@mock_aws
def test_threshold_is_configurable() -> None:
    session = boto3.Session(region_name=REGION)
    create_nat(session, gb_per_day=5)

    assert idle_nat_gateways.check(session, REGION, Thresholds(nat_gb=100), now=LATER)


@mock_aws
def test_skips_new_nat_gateway() -> None:
    session = boto3.Session(region_name=REGION)
    create_nat(session, gb_per_day=None)

    assert idle_nat_gateways.check(session, REGION, Thresholds(), now=days_later(5)) == []


def test_check_is_registered() -> None:
    assert idle_nat_gateways.check in CHECKS
