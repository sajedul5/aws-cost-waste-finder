import boto3
from helpers import MB, REGION, days_later, put_daily
from moto import mock_aws

from cost_waste_finder.checks import CHECKS, idle_ec2
from cost_waste_finder.config import Thresholds

LATER = days_later(15)  # metrics are put in the 14 days before this


def launch(session: boto3.Session, windows: bool = False) -> str:
    ec2 = session.client("ec2")
    images = ec2.describe_images()["Images"]
    image_id = next(i["ImageId"] for i in images if (i.get("Platform") == "windows") == windows)
    return ec2.run_instances(ImageId=image_id, InstanceType="t3.micro", MinCount=1, MaxCount=1)[
        "Instances"
    ][0]["InstanceId"]


def put_usage(session: boto3.Session, instance_id: str, cpu: float, mb_per_day: float) -> None:
    cloudwatch = session.client("cloudwatch")
    dims = {"InstanceId": instance_id}
    put_daily(cloudwatch, "AWS/EC2", "CPUUtilization", dims, cpu, LATER)
    put_daily(cloudwatch, "AWS/EC2", "NetworkIn", dims, mb_per_day / 2 * MB, LATER)
    put_daily(cloudwatch, "AWS/EC2", "NetworkOut", dims, mb_per_day / 2 * MB, LATER)


@mock_aws
def test_finds_idle_instance() -> None:
    session = boto3.Session(region_name=REGION)
    instance_id = launch(session)
    put_usage(session, instance_id, cpu=1.0, mb_per_day=2.0)

    findings = idle_ec2.check(session, REGION, Thresholds(), now=LATER)

    assert [f.resource_id for f in findings] == [instance_id]
    finding = findings[0]
    assert finding.check == "idle-ec2"
    assert "t3.micro running, avg CPU 1.0%" in finding.reason
    assert "(14 days)" in finding.reason
    assert finding.details == {"instance_type": "t3.micro", "operating_system": "Linux"}


@mock_aws
def test_detects_windows() -> None:
    session = boto3.Session(region_name=REGION)
    put_usage(session, launch(session, windows=True), cpu=1.0, mb_per_day=2.0)

    findings = idle_ec2.check(session, REGION, Thresholds(), now=LATER)

    assert findings[0].details["operating_system"] == "Windows"


@mock_aws
def test_busy_cpu_is_not_idle() -> None:
    session = boto3.Session(region_name=REGION)
    put_usage(session, launch(session), cpu=50.0, mb_per_day=2.0)

    assert idle_ec2.check(session, REGION, Thresholds(), now=LATER) == []


@mock_aws
def test_busy_network_is_not_idle() -> None:
    session = boto3.Session(region_name=REGION)
    put_usage(session, launch(session), cpu=1.0, mb_per_day=100.0)

    assert idle_ec2.check(session, REGION, Thresholds(), now=LATER) == []


@mock_aws
def test_thresholds_are_configurable() -> None:
    session = boto3.Session(region_name=REGION)
    put_usage(session, launch(session), cpu=8.0, mb_per_day=2.0)

    assert idle_ec2.check(session, REGION, Thresholds(), now=LATER) == []
    assert idle_ec2.check(session, REGION, Thresholds(cpu_percent=10), now=LATER)


@mock_aws
def test_skips_instance_with_short_history() -> None:
    session = boto3.Session(region_name=REGION)
    instance_id = launch(session)
    cloudwatch = session.client("cloudwatch")
    put_daily(cloudwatch, "AWS/EC2", "CPUUtilization", {"InstanceId": instance_id}, 1.0, LATER, 5)

    assert idle_ec2.check(session, REGION, Thresholds(), now=LATER) == []


@mock_aws
def test_recently_restarted_but_idle_is_reported() -> None:
    """LaunchTime resets on stop/start; 14 days of CloudWatch data still counts."""
    session = boto3.Session(region_name=REGION)
    instance_id = launch(session)  # LaunchTime = now
    now = days_later(0)
    dims = {"InstanceId": instance_id}
    cloudwatch = session.client("cloudwatch")
    put_daily(cloudwatch, "AWS/EC2", "CPUUtilization", dims, 1.0, now)
    put_daily(cloudwatch, "AWS/EC2", "NetworkIn", dims, 1 * MB, now)

    findings = idle_ec2.check(session, REGION, Thresholds(), now=now)

    assert [f.resource_id for f in findings] == [instance_id]


@mock_aws
def test_skips_instance_without_metrics() -> None:
    session = boto3.Session(region_name=REGION)
    launch(session)

    assert idle_ec2.check(session, REGION, Thresholds(), now=LATER) == []


def test_check_is_registered() -> None:
    assert idle_ec2.check in CHECKS
