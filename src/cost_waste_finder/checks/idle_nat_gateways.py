"""Check: NAT Gateways that sent almost no data over the lookback period."""

from datetime import UTC, datetime, timedelta

import boto3

from cost_waste_finder.config import Thresholds
from cost_waste_finder.metrics import daily_values
from cost_waste_finder.models import Finding

CHECK_ID = "idle-nat-gateway"
BYTES_PER_GB = 1024**3


def check(
    session: boto3.Session, region: str, thresholds: Thresholds, now: datetime | None = None
) -> list[Finding]:
    ec2 = session.client("ec2", region_name=region)
    cloudwatch = session.client("cloudwatch", region_name=region)
    now = now or datetime.now(UTC)
    days = thresholds.lookback_days

    findings = []
    pages = ec2.get_paginator("describe_nat_gateways").paginate(
        Filters=[{"Name": "state", "Values": ["available"]}]
    )
    for page in pages:
        for nat in page["NatGateways"]:
            if nat["CreateTime"] > now - timedelta(days=days):
                continue  # not enough history yet
            dims = {"NatGatewayId": nat["NatGatewayId"]}
            sent_bytes = sum(
                daily_values(
                    cloudwatch, "AWS/NATGateway", "BytesOutToDestination", dims, "Sum", days, now
                )
                + daily_values(
                    cloudwatch, "AWS/NATGateway", "BytesOutToSource", dims, "Sum", days, now
                )
            )
            sent_gb = sent_bytes / BYTES_PER_GB
            if sent_gb >= thresholds.nat_gb:
                continue
            findings.append(
                Finding(
                    check=CHECK_ID,
                    resource_id=nat["NatGatewayId"],
                    region=region,
                    reason=f"NAT Gateway sent {sent_gb:.2f} GB in {days} days",
                )
            )
    return findings
