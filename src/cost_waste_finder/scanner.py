"""Runs every registered check in one or more regions and prices the findings."""

import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.exceptions import ClientError

from cost_waste_finder.checks import CHECKS
from cost_waste_finder.config import Thresholds
from cost_waste_finder.models import Finding
from cost_waste_finder.pricing import PricingClient, apply_costs

# Regions scanned at the same time. The work is waiting on AWS, so threads help a lot.
MAX_PARALLEL_REGIONS = 8


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
    """Scan regions in parallel. One PricingClient is shared so prices are cached across regions.

    Findings come back in the order of `regions`, whatever order the threads finish in.
    """
    if len(regions) == 1:
        return scan(session, regions[0], thresholds, pricing)

    shared = ThreadSafeSession(session)
    pricing = pricing or PricingClient(session)
    results: dict[str, list[Finding]] = {}
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REGIONS) as pool:
        futures = {
            pool.submit(scan, shared, region, thresholds, pricing): region for region in regions
        }
        for done, future in enumerate(as_completed(futures), start=1):
            region = futures[future]
            results[region] = future.result()
            print(f"Scanned {region} ({done}/{len(regions)})", file=sys.stderr)
    return [finding for region in regions for finding in results[region]]


class ThreadSafeSession:
    """boto3 Sessions aren't thread-safe, but their clients are: lock only client creation."""

    def __init__(self, session: boto3.Session) -> None:
        self._session = session
        self._lock = threading.Lock()

    def client(self, *args, **kwargs):
        with self._lock:
            return self._session.client(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._session, name)


def enabled_regions(session: boto3.Session, any_region: str) -> list[str]:
    """Regions enabled for this account (opt-in regions that aren't enabled are left out)."""
    ec2 = session.client("ec2", region_name=any_region)
    return sorted(r["RegionName"] for r in ec2.describe_regions()["Regions"])


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)
