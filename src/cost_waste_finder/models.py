"""Data models shared by checks, pricing, billing and the reports."""

from dataclasses import dataclass, field
from datetime import date
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


@dataclass
class MonthCost:
    """Total bill for one month (the current month is partial, with a projection)."""

    start: date  # first day of the month
    total: float  # USD; for the current month: so far (to yesterday)
    partial: bool = False
    projected: float | None = None  # current month only: so far + forecast
    projection_method: str | None = None  # "AWS forecast" or "simple projection"

    @property
    def label(self) -> str:
        return self.start.strftime("%b %Y")


@dataclass
class ServiceTrend:
    """One service's cost in each of the three months."""

    service: str
    month_2: float  # month before last
    month_1: float  # last full month
    current_so_far: float
    current_projected: float | None  # simple projection per service

    @property
    def change(self) -> float:
        """Last month vs the month before."""
        return round(self.month_1 - self.month_2, 2)


@dataclass
class BillSummary:
    as_of: date  # data runs to the day before this
    months: list[MonthCost]  # [month before last, last month, current month]
    services: list[ServiceTrend]  # sorted by last month's cost, biggest first
    api_calls: int  # Cost Explorer calls made (~$0.01 each)
