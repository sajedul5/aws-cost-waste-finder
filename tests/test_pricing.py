import json

import boto3
import pytest
from botocore.stub import Stubber

from cost_waste_finder.models import Finding
from cost_waste_finder.pricing import PricingClient, apply_costs, location_name

REGION = "ap-southeast-1"


def price_item(usd: str) -> str:
    """A minimal PriceList entry as the Pricing API returns it (a JSON string)."""
    return json.dumps(
        {
            "product": {"attributes": {"volumeApiName": "gp3"}},
            "terms": {
                "OnDemand": {
                    "SKU.TERM": {
                        "priceDimensions": {
                            "SKU.TERM.RATE": {"unit": "GB-Mo", "pricePerUnit": {"USD": usd}}
                        }
                    }
                }
            },
        }
    )


def ebs_request(volume_type: str) -> dict:
    return {
        "ServiceCode": "AmazonEC2",
        "Filters": [
            {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"},
            {"Type": "TERM_MATCH", "Field": "volumeApiName", "Value": volume_type},
            {"Type": "TERM_MATCH", "Field": "location", "Value": "Asia Pacific (Singapore)"},
        ],
        "MaxResults": 10,
    }


@pytest.fixture
def pricing() -> PricingClient:
    return PricingClient(boto3.Session(region_name=REGION))


def ebs_finding(volume_type: str = "gp3", size: int = 100) -> Finding:
    return Finding(
        check="unattached-ebs",
        resource_id="vol-0123456789abcdef0",
        region=REGION,
        reason="test",
        details={"volume_type": volume_type, "size_gib": size},
    )


def test_location_name() -> None:
    assert location_name("ap-southeast-1") == "Asia Pacific (Singapore)"
    assert location_name("ap-southeast-2") == "Asia Pacific (Sydney)"


def test_location_name_unknown_region() -> None:
    with pytest.raises(ValueError, match="Unknown AWS region"):
        location_name("xx-nowhere-1")


def test_pricing_client_uses_us_east_1(pricing: PricingClient) -> None:
    assert pricing._client.meta.region_name == "us-east-1"


def test_ebs_storage_price_sends_filters_and_parses(pricing: PricingClient) -> None:
    with Stubber(pricing._client) as stub:
        stub.add_response(
            "get_products", {"PriceList": [price_item("0.0960000000")]}, ebs_request("gp3")
        )
        assert pricing.ebs_storage_price(REGION, "gp3") == pytest.approx(0.096)
        stub.assert_no_pending_responses()


def test_cache_calls_api_once(pricing: PricingClient) -> None:
    with Stubber(pricing._client) as stub:
        # Only one response queued: a second API call would raise.
        stub.add_response("get_products", {"PriceList": [price_item("0.12")]}, ebs_request("gp2"))
        assert pricing.ebs_storage_price(REGION, "gp2") == pytest.approx(0.12)
        assert pricing.ebs_storage_price(REGION, "gp2") == pytest.approx(0.12)


def test_apply_costs_sets_monthly_cost(pricing: PricingClient) -> None:
    findings = [ebs_finding("gp3", 100), ebs_finding("gp3", 20)]
    with Stubber(pricing._client) as stub:
        stub.add_response("get_products", {"PriceList": [price_item("0.096")]}, ebs_request("gp3"))
        apply_costs(findings, pricing)

    assert [f.monthly_cost for f in findings] == [9.6, 1.92]


def test_missing_price_leaves_cost_none(pricing: PricingClient) -> None:
    finding = ebs_finding("gp3")
    with Stubber(pricing._client) as stub:
        stub.add_response("get_products", {"PriceList": []}, ebs_request("gp3"))
        apply_costs([finding], pricing)

    assert finding.monthly_cost is None


def test_unknown_check_is_left_alone(pricing: PricingClient) -> None:
    finding = Finding(check="something-else", resource_id="x", region=REGION, reason="test")
    apply_costs([finding], pricing)
    assert finding.monthly_cost is None
