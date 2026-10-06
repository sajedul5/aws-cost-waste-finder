"""Runs every registered check in one or more regions and prices the findings."""

import sys

import boto3
from botocore.exceptions import ClientError

from cost_waste_finder.checks import CHECKS
from cost_waste_finder.config import Thresholds
from cost_waste_finder.models import Finding
from cost_waste_finder.pricing import PricingClient, apply_costs


def scan(
    session: boto3.Session,
    region: str,
    thresholds: Thresholds | None = None,
    pricing: PricingClient | None = None,
) -> list[Finding]:
    """Run all checks in a region. Failing checks (e.g. AccessDenied) are skipped with a warning."""
    thresholds = thresholds or Thresholds()
    findings: list[Finding] = []
    for check in CHECKS:
        name = check.__module__.rsplit(".", 1)[-1]
        try:
            findings.extend(check(session, region, thresholds))
        except ClientError as error:
            warn(f"check {name} skipped in {region}: {error.response['Error']['Code']}")

    try:
        apply_costs(findings, pricing or PricingClient(session))
    except ClientError as error:
        warn(f"pricing unavailable, costs shown as n/a: {error.response['Error']['Code']}")
    return findings


def scan_regions(
    session: boto3.Session,
    regions: list[str],
    thresholds: Thresholds | None = None,
    pricing: PricingClient | None = None,
) -> list[Finding]:
    """Scan each region in turn. One PricingClient is shared so prices are cached across regions."""
    pricing = pricing or PricingClient(session)
    findings: list[Finding] = []
    for number, region in enumerate(regions, start=1):
        if len(regions) > 1:
            print(f"Scanning {region} ({number}/{len(regions)})...", file=sys.stderr)
        findings.extend(scan(session, region, thresholds, pricing))
    return findings


def enabled_regions(session: boto3.Session, any_region: str) -> list[str]:
    """Regions enabled for this account (opt-in regions that aren't enabled are left out)."""
    ec2 = session.client("ec2", region_name=any_region)
    return sorted(r["RegionName"] for r in ec2.describe_regions()["Regions"])


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)
