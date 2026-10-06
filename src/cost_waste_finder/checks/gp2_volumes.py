"""Check: attached gp2 volumes that would be cheaper as gp3."""

import boto3

from cost_waste_finder.config import Thresholds
from cost_waste_finder.models import Finding

CHECK_ID = "gp2-to-gp3"


def check(session: boto3.Session, region: str, thresholds: Thresholds) -> list[Finding]:
    ec2 = session.client("ec2", region_name=region)
    # Only in-use volumes: unattached ones are already reported by unattached-ebs.
    pages = ec2.get_paginator("describe_volumes").paginate(
        Filters=[
            {"Name": "volume-type", "Values": ["gp2"]},
            {"Name": "status", "Values": ["in-use"]},
        ]
    )

    findings = []
    for page in pages:
        for volume in page["Volumes"]:
            size = volume["Size"]
            findings.append(
                Finding(
                    check=CHECK_ID,
                    resource_id=volume["VolumeId"],
                    region=region,
                    reason=f"gp2 volume ({size} GiB) can be changed to gp3 with the same IOPS",
                    details={"size_gib": size},
                )
            )
    return findings
