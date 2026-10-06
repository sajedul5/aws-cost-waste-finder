"""Registry of waste checks. Each check is `check(session, region) -> list[Finding]`."""

from collections.abc import Callable

import boto3

from cost_waste_finder.checks import unattached_ebs
from cost_waste_finder.models import Finding

Check = Callable[[boto3.Session, str], list[Finding]]

CHECKS: list[Check] = [
    unattached_ebs.check,
]
