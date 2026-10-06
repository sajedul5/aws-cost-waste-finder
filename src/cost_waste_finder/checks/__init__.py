"""Registry of waste checks. Each is `check(session, region, thresholds) -> list[Finding]`."""

from collections.abc import Callable

import boto3

from cost_waste_finder.checks import (
    gp2_volumes,
    idle_ec2,
    idle_load_balancers,
    idle_nat_gateways,
    old_snapshots,
    stopped_ec2,
    unattached_ebs,
    unattached_eips,
)
from cost_waste_finder.config import Thresholds
from cost_waste_finder.models import Finding

Check = Callable[[boto3.Session, str, Thresholds], list[Finding]]

CHECKS: list[Check] = [
    unattached_ebs.check,
    old_snapshots.check,
    unattached_eips.check,
    gp2_volumes.check,
    idle_ec2.check,
    idle_nat_gateways.check,
    idle_load_balancers.check,
    stopped_ec2.check,
]
