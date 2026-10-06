"""Data models shared by checks, pricing and the report."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Finding:
    """One wasted resource found by a check."""

    check: str  # short check id, e.g. "unattached-ebs"
    resource_id: str
    region: str
    reason: str  # plain English, no account IDs or ARNs
    details: dict[str, Any] = field(default_factory=dict)  # inputs for pricing
    monthly_cost: float | None = None  # USD, filled in by the pricing layer
