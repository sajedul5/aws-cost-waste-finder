"""AWS Pricing API client with an in-memory cache, and monthly cost estimates for findings."""

import json
from collections.abc import Callable

import boto3
import botocore.session

from cost_waste_finder.models import Finding

# The Pricing API is only served from a few regions; prices for every region are available here.
PRICING_REGION = "us-east-1"


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

    def get_price(self, service_code: str, filters: dict[str, str]) -> float | None:
        key = (service_code, tuple(sorted(filters.items())))
        if key not in self._cache:
            self._cache[key] = self._fetch_price(service_code, filters)
        return self._cache[key]

    def _fetch_price(self, service_code: str, filters: dict[str, str]) -> float | None:
        response = self._client.get_products(
            ServiceCode=service_code,
            Filters=[
                {"Type": "TERM_MATCH", "Field": field, "Value": value}
                for field, value in filters.items()
            ],
            MaxResults=10,
        )
        for item in response["PriceList"]:
            price = _on_demand_usd(json.loads(item))
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


COST_FUNCTIONS: dict[str, Callable[[Finding, PricingClient], float | None]] = {
    "unattached-ebs": _unattached_ebs_cost,
}


def apply_costs(findings: list[Finding], pricing: PricingClient) -> None:
    """Fill in monthly_cost for each finding. Unknown prices stay None."""
    for finding in findings:
        cost_function = COST_FUNCTIONS.get(finding.check)
        if cost_function:
            finding.monthly_cost = cost_function(finding, pricing)
