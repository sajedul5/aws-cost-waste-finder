"""Check: running EC2 instances with very low CPU and network over the lookback period."""

from datetime import UTC, datetime

import boto3

from cost_waste_finder.config import Thresholds
from cost_waste_finder.metrics import average, daily_values
from cost_waste_finder.models import Finding

CHECK_ID = "idle-ec2"
BYTES_PER_MB = 1024**2
# Days of data that may be missing at the window edges and still count as "enough history".
MISSING_DAYS_ALLOWED = 1


def check(
    session: boto3.Session, region: str, thresholds: Thresholds, now: datetime | None = None
) -> list[Finding]:
    ec2 = session.client("ec2", region_name=region)
    cloudwatch = session.client("cloudwatch", region_name=region)
    now = now or datetime.now(UTC)

    findings = []
    pages = ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )
    for page in pages:
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                finding = _idle_finding(cloudwatch, instance, region, thresholds, now)
                if finding:
                    findings.append(finding)
    return findings


def _idle_finding(
    cloudwatch, instance: dict, region: str, thresholds: Thresholds, now: datetime
) -> Finding | None:
    days = thresholds.lookback_days
    dims = {"InstanceId": instance["InstanceId"]}

    # History comes from CloudWatch, not LaunchTime: LaunchTime resets on every stop/start.
    cpu_days = daily_values(cloudwatch, "AWS/EC2", "CPUUtilization", dims, "Average", days, now)
    if len(cpu_days) < days - MISSING_DAYS_ALLOWED:
        return None  # not enough history yet
    cpu = average(cpu_days)
    if cpu >= thresholds.cpu_percent:
        return None

    network_bytes = sum(
        daily_values(cloudwatch, "AWS/EC2", "NetworkIn", dims, "Sum", days, now)
        + daily_values(cloudwatch, "AWS/EC2", "NetworkOut", dims, "Sum", days, now)
    )
    mb_per_day = network_bytes / BYTES_PER_MB / days
    if mb_per_day >= thresholds.network_mb_per_day:
        return None

    instance_type = instance["InstanceType"]
    return Finding(
        check=CHECK_ID,
        resource_id=instance["InstanceId"],
        region=region,
        reason=(
            f"{instance_type} running, avg CPU {cpu:.1f}%, "
            f"network {mb_per_day:.1f} MB/day ({days} days)"
        ),
        details={
            "instance_type": instance_type,
            "operating_system": "Windows" if instance.get("Platform") == "windows" else "Linux",
        },
    )
