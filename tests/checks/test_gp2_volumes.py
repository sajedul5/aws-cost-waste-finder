import boto3
from moto import mock_aws

from cost_waste_finder.checks import CHECKS, gp2_volumes
from cost_waste_finder.config import Thresholds

REGION = "ap-southeast-1"
AZ = f"{REGION}a"


@mock_aws
def test_finds_only_attached_gp2() -> None:
    session = boto3.Session(region_name=REGION)
    ec2 = session.client("ec2")
    image_id = ec2.describe_images()["Images"][0]["ImageId"]
    instance_id = ec2.run_instances(ImageId=image_id, MinCount=1, MaxCount=1)["Instances"][0][
        "InstanceId"
    ]

    def volume(volume_type: str, size: int, device: str | None) -> str:
        volume_id = ec2.create_volume(AvailabilityZone=AZ, Size=size, VolumeType=volume_type)[
            "VolumeId"
        ]
        if device:
            ec2.attach_volume(VolumeId=volume_id, InstanceId=instance_id, Device=device)
        return volume_id

    attached_gp2 = volume("gp2", 200, "/dev/sdf")
    attached_gp3 = volume("gp3", 200, "/dev/sdg")
    unattached_gp2 = volume("gp2", 200, None)  # reported by unattached-ebs instead

    findings = {f.resource_id: f for f in gp2_volumes.check(session, REGION, Thresholds())}

    # moto also gives the instance a gp2 root volume, which is correctly reported too.
    assert attached_gp2 in findings
    assert attached_gp3 not in findings
    assert unattached_gp2 not in findings
    finding = findings[attached_gp2]
    assert finding.check == "gp2-to-gp3"
    assert finding.details == {"size_gib": 200}
    assert "200 GiB" in finding.reason


@mock_aws
def test_no_volumes_no_findings() -> None:
    assert gp2_volumes.check(boto3.Session(region_name=REGION), REGION, Thresholds()) == []


def test_check_is_registered() -> None:
    assert gp2_volumes.check in CHECKS
