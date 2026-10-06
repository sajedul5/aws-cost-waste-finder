"""AWS Pricing API client with an in-memory cache, and monthly cost estimates for findings."""

import json
from collections.abc import Callable

import boto3
import botocore.session

from cost_waste_finder.models import Finding

# The Pricing API is only served from a few regions; prices for every region are available here.
PRICING_REGION = "us-east-1"
HOURS_PER_MONTH = 730

# gp2 baseline performance is 3 IOPS per GiB (max 16,000); gp3 includes 3,000 IOPS for free.
GP2_IOPS_PER_GIB = 3
GP2_MAX_IOPS = 16_000
GP3_FREE_IOPS = 3_000


def location_name(region: str) -> str:
    """Map a region code to the Pricing API location, e.g. "Asia Pacific (Singapore)"."""
    endpoints = botocore.session.get_session().get_data("endpoints")
    for partition in endpoints["partitions"]:
        if region in partition["regions"]:
            return partition["regions"][region]["description"]
    raise ValueError(f"Unknown AWS region: {region}")


class PricingClient:
    """Looks up on-demand USD prices. Each distinct lookup hits the API once per run."""

    def __init__(self, session: boto3.Session) -> None:
        self._client = session.client("pricing", region_name=PRICING_REGION)
        self._cache: dict[tuple, float | None] = {}

    def get_price(
        self, service_code: str, filters: dict[str, str], usagetype_suffix: str | None = None
    ) -> float | None:
        """First non-zero on-demand USD price matching the filters.

        usagetype_suffix picks a product whose usagetype ends with it; usagetypes start with a
        region code (e.g. "APS1-EBS:SnapshotUsage"), so they can't be matched exactly.
        """
        key = (service_code, tuple(sorted(filters.items())), usagetype_suffix)
        if key not in self._cache:
            self._cache[key] = self._fetch_price(service_code, filters, usagetype_suffix)
        return self._cache[key]

    def _fetch_price(
        self, service_code: str, filters: dict[str, str], usagetype_suffix: str | None
    ) -> float | None:
        response = self._client.get_products(
            ServiceCode=service_code,
            Filters=[
                {"Type": "TERM_MATCH", "Field": field, "Value": value}
                for field, value in filters.items()
            ],
            MaxResults=100,
        )
        for item in response["PriceList"]:
            product = json.loads(item)
            usagetype = product.get("product", {}).get("attributes", {}).get("usagetype", "")
            if usagetype_suffix and not usagetype.endswith(usagetype_suffix):
                continue
            price = _on_demand_usd(product)
            if price:
                return price
        return None

    def ebs_storage_price(self, region: str, volume_type: str) -> float | None:
        """USD per GB-month of EBS storage for a volume type (gp2, gp3, io1, ...)."""
        return self.get_price(
            "AmazonEC2",
            {
                "productFamily": "Storage",
                "volumeApiName": volume_type,
                "location": location_name(region),
            },
        )

    def gp3_iops_price(self, region: str) -> float | None:
        """USD per provisioned IOPS-month above the gp3 free 3,000."""
        return self.get_price(
            "AmazonEC2",
            {
                "productFamily": "System Operation",
                "volumeApiName": "gp3",
                "location": location_name(region),
            },
        )

    def snapshot_price(self, region: str, archive: bool = False) -> float | None:
        """USD per GB-month of EBS snapshot storage (standard or archive tier)."""
        suffix = "EBS:SnapshotArchiveStorage" if archive else "EBS:SnapshotUsage"
        return self.get_price(
            "AmazonEC2",
            {
                "productFamily": "Storage Snapshot",
                "storageMedia": "Amazon S3",
                "location": location_name(region),
            },
            usagetype_suffix=suffix,
        )

    def idle_ipv4_hourly_price(self, region: str) -> float | None:
        """USD per hour for a public IPv4 address that isn't in use."""
        return self.get_price(
            "AmazonVPC",
            {"group": "VPCPublicIPv4Address", "location": location_name(region)},
            usagetype_suffix="PublicIPv4:IdleAddress",
        )


def _on_demand_usd(product: dict) -> float | None:
    for term in product.get("terms", {}).get("OnDemand", {}).values():
        for dimension in term["priceDimensions"].values():
            usd = dimension["pricePerUnit"].get("USD")
            if usd is not None:
                return float(usd)
    return None


def _unattached_ebs_cost(finding: Finding, pricing: PricingClient) -> float | None:
    # Storage only: extra provisioned IOPS/throughput are not included yet (under-estimate).
    price = pricing.ebs_storage_price(finding.region, finding.details["volume_type"])
    if price is None:
        return None
    return round(finding.details["size_gib"] * price, 2)


def _old_snapshot_cost(finding: Finding, pricing: PricingClient) -> float | None:
    price = pricing.snapshot_price(finding.region, archive=finding.details["archive"])
    if price is None:
        return None
    return round(finding.details["size_gib"] * price, 2)


def _unattached_eip_cost(finding: Finding, pricing: PricingClient) -> float | None:
    price = pricing.idle_ipv4_hourly_price(finding.region)
    if price is None:
        return None
    return round(price * HOURS_PER_MONTH, 2)


def _gp2_to_gp3_savings(finding: Finding, pricing: PricingClient) -> float | None:
    """gp2 cost minus the gp3 cost for the same size and the same baseline IOPS."""
    size = finding.details["size_gib"]
    gp2 = pricing.ebs_storage_price(finding.region, "gp2")
    gp3 = pricing.ebs_storage_price(finding.region, "gp3")
    iops = pricing.gp3_iops_price(finding.region)
    if gp2 is None or gp3 is None or iops is None:
        return None
    extra_iops = max(0, min(size * GP2_IOPS_PER_GIB, GP2_MAX_IOPS) - GP3_FREE_IOPS)
    savings = size * (gp2 - gp3) - extra_iops * iops
    return round(max(0.0, savings), 2)


COST_FUNCTIONS: dict[str, Callable[[Finding, PricingClient], float | None]] = {
    "unattached-ebs": _unattached_ebs_cost,
    "old-snapshot": _old_snapshot_cost,
    "unattached-eip": _unattached_eip_cost,
    "gp2-to-gp3": _gp2_to_gp3_savings,
}


def apply_costs(findings: list[Finding], pricing: PricingClient) -> None:
    """Fill in monthly_cost (the monthly saving) for each finding. Unknown prices stay None."""
    for finding in findings:
        cost_function = COST_FUNCTIONS.get(finding.check)
        if cost_function:
            finding.monthly_cost = cost_function(finding, pricing)
