from datetime import UTC, datetime

import boto3
import pytest
from helpers import REGION, days_later
from moto import mock_aws

from cost_waste_finder.checks import CHECKS, stopped_ec2
from cost_waste_finder.config import Thresholds


def launch(session: boto3.Session, stop: bool = True, extra_gib: int | None = None) -> str:
    """Start an instance (moto adds an 8 GiB root volume), maybe add a disk, then stop it."""
    ec2 = session.client("ec2")
    image_id = ec2.describe_images()["Images"][0]["ImageId"]
    instance_id = ec2.run_instances(
        ImageId=image_id, InstanceType="t3.micro", MinCount=1, MaxCount=1
    )["Instances"][0]["InstanceId"]
    if extra_gib:
        volume_id = ec2.create_volume(
            AvailabilityZone=f"{REGION}a", Size=extra_gib, VolumeType="gp3"
        )["VolumeId"]
        ec2.attach_volume(VolumeId=volume_id, InstanceId=instance_id, Device="/dev/sdf")
    if stop:
        ec2.stop_instances(InstanceIds=[instance_id])
    return instance_id


@mock_aws
def test_finds_instance_stopped_longer_than_threshold() -> None:
    session = boto3.Session(region_name=REGION)
    instance_id = launch(session, extra_gib=100)

    findings = stopped_ec2.check(session, REGION, Thresholds(), now=days_later(31))

    assert [f.resource_id for f in findings] == [instance_id]
    finding = findings[0]
    assert finding.check == "stopped-ec2"
    assert finding.region == REGION
    assert "t3.micro stopped 31 days" in finding.reason
    assert "2 volumes" in finding.reason
    assert finding.details["stopped_days"] == 31
    assert sorted(v["volume_type"] for v in finding.details["volumes"]) == ["gp2", "gp3"]
    assert sum(v["size_gib"] for v in finding.details["volumes"]) == 100 + 8


@mock_aws
def test_ignores_recently_stopped_instance() -> None:
    session = boto3.Session(region_name=REGION)
    launch(session)

    assert stopped_ec2.check(session, REGION, Thresholds(), now=days_later(29)) == []


@mock_aws
def test_threshold_is_configurable() -> None:
    session = boto3.Session(region_name=REGION)
    launch(session)

    assert stopped_ec2.check(session, REGION, Thresholds(stopped_days=7), now=days_later(8))


@mock_aws
def test_ignores_running_instance() -> None:
    session = boto3.Session(region_name=REGION)
    launch(session, stop=False)

    assert stopped_ec2.check(session, REGION, Thresholds(), now=days_later(31)) == []


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("User initiated (2026-07-25 10:00:00 GMT)", datetime(2026, 7, 25, 10, tzinfo=UTC)),
        ("User initiated (2026-07-25 10:00:00 UTC)", datetime(2026, 7, 25, 10, tzinfo=UTC)),
        ("Server.SpotInstanceTermination", None),
        ("", None),
    ],
)
def test_stopped_time(reason: str, expected: datetime | None) -> None:
    assert stopped_ec2.stopped_time(reason) == expected


def test_check_is_registered() -> None:
    assert stopped_ec2.check in CHECKS
