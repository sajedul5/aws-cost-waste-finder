import boto3
from moto import mock_aws

from cost_waste_finder.checks import CHECKS, unattached_ebs

REGION = "ap-southeast-1"
AZ = f"{REGION}a"


def make_session() -> boto3.Session:
    return boto3.Session(region_name=REGION)


@mock_aws
def test_finds_only_unattached_volume() -> None:
    session = make_session()
    ec2 = session.client("ec2")
    image_id = ec2.describe_images()["Images"][0]["ImageId"]
    instance_id = ec2.run_instances(ImageId=image_id, MinCount=1, MaxCount=1)["Instances"][0][
        "InstanceId"
    ]
    attached = ec2.create_volume(AvailabilityZone=AZ, Size=50, VolumeType="gp3")["VolumeId"]
    ec2.attach_volume(VolumeId=attached, InstanceId=instance_id, Device="/dev/sdf")
    unattached = ec2.create_volume(AvailabilityZone=AZ, Size=100, VolumeType="gp2")["VolumeId"]

    findings = unattached_ebs.check(session, REGION)

    assert [f.resource_id for f in findings] == [unattached]
    finding = findings[0]
    assert finding.check == "unattached-ebs"
    assert finding.region == REGION
    assert "100 GiB gp2" in finding.reason
    assert finding.details["volume_type"] == "gp2"
    assert finding.details["size_gib"] == 100
    assert finding.monthly_cost is None


@mock_aws
def test_empty_account_has_no_findings() -> None:
    assert unattached_ebs.check(make_session(), REGION) == []


@mock_aws
def test_only_scans_given_region() -> None:
    other = boto3.Session(region_name="us-east-1").client("ec2")
    other.create_volume(AvailabilityZone="us-east-1a", Size=10)

    assert unattached_ebs.check(make_session(), REGION) == []


@mock_aws
def test_finds_many_volumes() -> None:
    session = make_session()
    ec2 = session.client("ec2")
    created = {ec2.create_volume(AvailabilityZone=AZ, Size=1)["VolumeId"] for _ in range(10)}

    findings = unattached_ebs.check(session, REGION)

    assert {f.resource_id for f in findings} == created


def test_check_is_registered() -> None:
    assert unattached_ebs.check in CHECKS
