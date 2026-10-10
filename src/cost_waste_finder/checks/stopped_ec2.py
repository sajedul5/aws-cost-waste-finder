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

    candidates = []  # (instance, days stopped, volume IDs)
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
                if days > thresholds.stopped_days and volume_ids:
                    candidates.append((instance, days, volume_ids))
    if not candidates:
        return []

    # One paginated call for every volume. A filter (not VolumeIds) so that a volume deleted
    # during the scan is just missing instead of failing the whole call.
    all_ids = [volume_id for _, _, ids in candidates for volume_id in ids]
    volumes_by_id = {}
    for start in range(0, len(all_ids), 200):
        pages = ec2.get_paginator("describe_volumes").paginate(
            Filters=[{"Name": "volume-id", "Values": all_ids[start : start + 200]}]
        )
        for page in pages:
            for v in page["Volumes"]:
                volumes_by_id[v["VolumeId"]] = {
                    "volume_id": v["VolumeId"],
                    "volume_type": v["VolumeType"],
                    "size_gib": v["Size"],
                }

    findings = []
    for instance, days, volume_ids in candidates:
        volumes = [volumes_by_id[i] for i in volume_ids if i in volumes_by_id]
        if not volumes:
            continue
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
