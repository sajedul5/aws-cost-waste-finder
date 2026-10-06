"""Runs every registered check in a region and prices the findings."""

import sys

import boto3
from botocore.exceptions import ClientError

from cost_waste_finder.checks import CHECKS
from cost_waste_finder.models import Finding
from cost_waste_finder.pricing import PricingClient, apply_costs


def scan(
    session: boto3.Session, region: str, pricing: PricingClient | None = None
) -> list[Finding]:
    """Run all checks in a region. Failing checks (e.g. AccessDenied) are skipped with a warning."""
    findings: list[Finding] = []
    for check in CHECKS:
        name = check.__module__.rsplit(".", 1)[-1]
        try:
            findings.extend(check(session, region))
        except ClientError as error:
            warn(f"check {name} skipped in {region}: {error.response['Error']['Code']}")

    try:
        apply_costs(findings, pricing or PricingClient(session))
    except ClientError as error:
        warn(f"pricing unavailable, costs shown as n/a: {error.response['Error']['Code']}")
    return findings


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)
