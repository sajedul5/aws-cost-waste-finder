"""Check: EC2 instances stopped for a long time that still pay for their EBS volumes."""

import re
from datetime import UTC, datetime

import boto3

from cost_waste_finder.config import Thresholds
from cost_waste_finder.models import Finding

CHECK_ID = "stopped-ec2"

# e.g. "User initiated (2026-07-25 10:00:00 GMT)"
STOPPED_AT = re.compile(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?:GMT|UTC)\)")


def check(
    session: boto3.Session, region: str, thresholds: Thresholds, now: datetime | None = None
) -> list[Finding]:
    ec2 = session.client("ec2", region_name=region)
    now = now or datetime.now(UTC)

    findings = []
    pages = ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    )
    for page in pages:
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                stopped_at = stopped_time(instance.get("StateTransitionReason", ""))
                if stopped_at is None:
                    continue  # stop time unknown: don't guess
                days = (now - stopped_at).days
                volume_ids = [
                    m["Ebs"]["VolumeId"]
                    for m in instance.get("BlockDeviceMappings", [])
                    if "Ebs" in m
                ]
                if days <= thresholds.stopped_days or not volume_ids:
                    continue
                volumes = [
                    {"volume_type": v["VolumeType"], "size_gib": v["Size"]}
                    for v in ec2.describe_volumes(VolumeIds=volume_ids)["Volumes"]
                ]
                total_gib = sum(v["size_gib"] for v in volumes)
                count = len(volumes)
                findings.append(
                    Finding(
                        check=CHECK_ID,
                        resource_id=instance["InstanceId"],
                        region=region,
                        reason=(
                            f"{instance['InstanceType']} stopped {days} days, still paying for "
                            f"{count} volume{'s' if count != 1 else ''} ({total_gib} GiB)"
                        ),
                        details={"volumes": volumes, "stopped_days": days},
                    )
                )
    return findings


def stopped_time(reason: str) -> datetime | None:
    match = STOPPED_AT.search(reason)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
