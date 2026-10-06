"""Check: Elastic IPs not associated with an instance or network interface."""

import boto3

from cost_waste_finder.config import Thresholds
from cost_waste_finder.models import Finding

CHECK_ID = "unattached-eip"


def check(session: boto3.Session, region: str, thresholds: Thresholds) -> list[Finding]:
    ec2 = session.client("ec2", region_name=region)
    # DescribeAddresses has no paginator: it returns every address in one call.
    addresses = ec2.describe_addresses()["Addresses"]

    return [
        Finding(
            check=CHECK_ID,
            resource_id=address.get("AllocationId") or address["PublicIp"],
            region=region,
            reason="Elastic IP not associated with any instance or network interface",
        )
        for address in addresses
        if "AssociationId" not in address
    ]
