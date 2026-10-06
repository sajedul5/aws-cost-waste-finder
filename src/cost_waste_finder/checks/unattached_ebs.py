"""Check: EBS volumes not attached to any instance (status "available")."""

import boto3

from cost_waste_finder.config import Thresholds
from cost_waste_finder.models import Finding

CHECK_ID = "unattached-ebs"


def check(session: boto3.Session, region: str, thresholds: Thresholds) -> list[Finding]:
    ec2 = session.client("ec2", region_name=region)
    paginator = ec2.get_paginator("describe_volumes")
    pages = paginator.paginate(Filters=[{"Name": "status", "Values": ["available"]}])

    findings = []
    for page in pages:
        for volume in page["Volumes"]:
            size = volume["Size"]
            volume_type = volume["VolumeType"]
            findings.append(
                Finding(
                    check=CHECK_ID,
                    resource_id=volume["VolumeId"],
                    region=region,
                    reason=f"Unattached volume (status available), {size} GiB {volume_type}",
                    details={
                        "volume_type": volume_type,
                        "size_gib": size,
                        "iops": volume.get("Iops"),
                        "throughput": volume.get("Throughput"),
                    },
                )
            )
    return findings
