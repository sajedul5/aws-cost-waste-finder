"""Runs every registered check in one or more regions and prices the findings."""

import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.exceptions import ClientError, HTTPClientError
from botocore.exceptions import ConnectionError as AwsConnectionError

from cost_waste_finder.checks import CHECKS
from cost_waste_finder.config import Thresholds
from cost_waste_finder.models import Finding
from cost_waste_finder.pricing import PricingClient, apply_costs

# Errors that skip one check (or pricing) with a warning: API errors such as AccessDenied, and
# network problems in one region (unreachable endpoint, timeouts). Credential errors are not here:
# they affect every call, so they stop the scan with a clear message instead of a $0 report.
SKIPPABLE_ERRORS = (ClientError, HTTPClientError, AwsConnectionError)

# Regions scanned at the same time. The work is waiting on AWS, so threads help a lot.
MAX_PARALLEL_REGIONS = 8


def scan(
    session: boto3.Session,
    region: str,
    thresholds: Thresholds | None = None,
    pricing: PricingClient | None = None,
) -> list[Finding]:
    """Run all checks in a region. A failing check (e.g. AccessDenied, a timeout) is skipped
    with a warning, so one problem never hides the other findings."""
    thresholds = thresholds or Thresholds()
    findings: list[Finding] = []
    for check in CHECKS:
        name = check.__module__.rsplit(".", 1)[-1]
        try:
            findings.extend(check(session, region, thresholds))
        except SKIPPABLE_ERRORS as error:
            warn(f"check {name} skipped in {region}: {error_code(error)}")
    findings = remove_overlaps(findings)

    try:
        apply_costs(findings, pricing or PricingClient(session))
    except SKIPPABLE_ERRORS as error:
        warn(f"pricing unavailable, costs shown as n/a: {error_code(error)}")
    return findings


def remove_overlaps(findings: list[Finding]) -> list[Finding]:
    """Count each dollar of waste once.

    A stopped instance's volumes are still "in-use", so a gp2 volume on it would be reported by
    gp2-to-gp3 and also be part of the stopped-ec2 storage cost. Deleting the volume saves the
    full storage cost; converting it to gp3 first saves nothing extra. Keep only stopped-ec2.
    """
    on_stopped = {
        volume["volume_id"]
        for f in findings
        if f.check == "stopped-ec2"
        for volume in f.details["volumes"]
    }
    return [f for f in findings if not (f.check == "gp2-to-gp3" and f.resource_id in on_stopped)]


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


def error_code(error: Exception) -> str:
    if isinstance(error, ClientError):
        return error.response["Error"]["Code"]
    return type(error).__name__  # e.g. EndpointConnectionError, ReadTimeoutError


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)
