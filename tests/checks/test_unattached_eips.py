import boto3
from moto import mock_aws

from cost_waste_finder.checks import CHECKS, unattached_eips

REGION = "ap-southeast-1"


def make_session() -> boto3.Session:
    return boto3.Session(region_name=REGION)


@mock_aws
def test_finds_only_unassociated_eip() -> None:
    session = make_session()
    ec2 = session.client("ec2")
    image_id = ec2.describe_images()["Images"][0]["ImageId"]
    instance_id = ec2.run_instances(ImageId=image_id, MinCount=1, MaxCount=1)["Instances"][0][
        "InstanceId"
    ]
    associated = ec2.allocate_address(Domain="vpc")["AllocationId"]
    ec2.associate_address(AllocationId=associated, InstanceId=instance_id)
    idle = ec2.allocate_address(Domain="vpc")["AllocationId"]

    findings = unattached_eips.check(session, REGION)

    assert [f.resource_id for f in findings] == [idle]
    assert findings[0].check == "unattached-eip"
    assert findings[0].region == REGION
    assert "not associated" in findings[0].reason


@mock_aws
def test_no_addresses_no_findings() -> None:
    assert unattached_eips.check(make_session(), REGION) == []


@mock_aws
def test_only_scans_given_region() -> None:
    boto3.client("ec2", region_name="us-east-1").allocate_address(Domain="vpc")

    assert unattached_eips.check(make_session(), REGION) == []


def test_check_is_registered() -> None:
    assert unattached_eips.check in CHECKS
