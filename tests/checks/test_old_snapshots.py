from datetime import UTC, datetime, timedelta

import boto3
from moto import mock_aws

from cost_waste_finder.checks import CHECKS, old_snapshots
from cost_waste_finder.config import Thresholds

REGION = "ap-southeast-1"
DEFAULTS = Thresholds()


def make_session() -> boto3.Session:
    return boto3.Session(region_name=REGION)


def create_snapshot(ec2, size: int = 20) -> str:
    az = f"{ec2.meta.region_name}a"
    volume_id = ec2.create_volume(AvailabilityZone=az, Size=size)["VolumeId"]
    return ec2.create_snapshot(VolumeId=volume_id)["SnapshotId"]


def days_later(days: int) -> datetime:
    """moto stamps snapshots with the current time, so we move "now" forward instead."""
    return datetime.now(UTC) + timedelta(days=days)


def builtin_snapshots(session: boto3.Session) -> set[str]:
    """moto's fake account already owns the snapshots behind its built-in AMIs."""
    pages = session.client("ec2").get_paginator("describe_snapshots").paginate(OwnerIds=["self"])
    return {s["SnapshotId"] for page in pages for s in page["Snapshots"]}


def run_check(
    session: boto3.Session, ignore: set[str], thresholds: Thresholds = DEFAULTS, **kwargs
) -> list:
    findings = old_snapshots.check(session, REGION, thresholds, **kwargs)
    return [f for f in findings if f.resource_id not in ignore]


@mock_aws
def test_finds_snapshot_older_than_threshold() -> None:
    session = make_session()
    ignore = builtin_snapshots(session)
    snapshot_id = create_snapshot(session.client("ec2"), size=20)

    findings = run_check(session, ignore, now=days_later(91))

    assert [f.resource_id for f in findings] == [snapshot_id]
    finding = findings[0]
    assert finding.check == "old-snapshot"
    assert finding.region == REGION
    assert "91 days old" in finding.reason
    assert "up to 20 GiB" in finding.reason
    assert finding.details == {"size_gib": 20, "age_days": 91, "archive": False}


@mock_aws
def test_ignores_snapshot_younger_than_threshold() -> None:
    session = make_session()
    ignore = builtin_snapshots(session)
    create_snapshot(session.client("ec2"))

    assert run_check(session, ignore, now=days_later(89)) == []


@mock_aws
def test_threshold_is_configurable() -> None:
    session = make_session()
    ignore = builtin_snapshots(session)
    create_snapshot(session.client("ec2"))

    assert run_check(session, ignore, Thresholds(snapshot_age_days=30), now=days_later(31))


@mock_aws
def test_ignores_snapshot_used_by_ami() -> None:
    session = make_session()
    ignore = builtin_snapshots(session)
    ec2 = session.client("ec2")
    unused = create_snapshot(ec2)
    # moto creates the AMI's root snapshot itself, so read back which snapshot it uses.
    image_id = ec2.register_image(Name="test-ami", RootDeviceName="/dev/sda1")["ImageId"]
    image = ec2.describe_images(ImageIds=[image_id])["Images"][0]
    used = image["BlockDeviceMappings"][0]["Ebs"]["SnapshotId"]

    found = {f.resource_id for f in run_check(session, ignore, now=days_later(91))}

    assert unused in found
    assert used not in found


@mock_aws
def test_only_scans_given_region() -> None:
    session = make_session()
    ignore = builtin_snapshots(session)
    create_snapshot(boto3.client("ec2", region_name="us-east-1"))

    assert run_check(session, ignore, now=days_later(91)) == []


def test_check_is_registered() -> None:
    assert old_snapshots.check in CHECKS
