"""Registry of waste checks. Each check is `check(session, region) -> list[Finding]`."""

from collections.abc import Callable

import boto3

from cost_waste_finder.checks import gp2_volumes, old_snapshots, unattached_ebs, unattached_eips
from cost_waste_finder.models import Finding

Check = Callable[[boto3.Session, str], list[Finding]]

CHECKS: list[Check] = [
    unattached_ebs.check,
    old_snapshots.check,
    unattached_eips.check,
    gp2_volumes.check,
]
