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
        "MaxResults": 100,
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


def priced_item(usagetype: str, usd: str) -> str:
    item = json.loads(price_item(usd))
    item["product"]["attributes"]["usagetype"] = usagetype
    return json.dumps(item)


def snapshot_request() -> dict:
    return {
        "ServiceCode": "AmazonEC2",
        "Filters": [
            {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage Snapshot"},
            {"Type": "TERM_MATCH", "Field": "storageMedia", "Value": "Amazon S3"},
            {"Type": "TERM_MATCH", "Field": "location", "Value": "Asia Pacific (Singapore)"},
        ],
        "MaxResults": 100,
    }


def test_snapshot_price_picks_matching_usagetype(pricing: PricingClient) -> None:
    products = [
        priced_item("APS1-EBS:SnapshotArchiveStorage", "0.0125"),
        priced_item("APS1-EBS:SnapshotUsage.outposts", "0.027"),
        priced_item("APS1-EBS:SnapshotUsage", "0.05"),
    ]
    with Stubber(pricing._client) as stub:
        stub.add_response("get_products", {"PriceList": products}, snapshot_request())
        stub.add_response("get_products", {"PriceList": products}, snapshot_request())
        assert pricing.snapshot_price(REGION) == pytest.approx(0.05)
        assert pricing.snapshot_price(REGION, archive=True) == pytest.approx(0.0125)


def test_idle_ipv4_price(pricing: PricingClient) -> None:
    request = {
        "ServiceCode": "AmazonVPC",
        "Filters": [
            {"Type": "TERM_MATCH", "Field": "group", "Value": "VPCPublicIPv4Address"},
            {"Type": "TERM_MATCH", "Field": "location", "Value": "Asia Pacific (Singapore)"},
        ],
        "MaxResults": 100,
    }
    products = [
        priced_item("APS1-PublicIPv4:InUseAddress", "0.006"),
        priced_item("APS1-PublicIPv4:IdleAddress", "0.005"),
    ]
    with Stubber(pricing._client) as stub:
        stub.add_response("get_products", {"PriceList": products}, request)
        assert pricing.idle_ipv4_hourly_price(REGION) == pytest.approx(0.005)


@pytest.fixture
def singapore_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real Singapore prices (Oct 2026) without API calls."""
    storage = {"gp2": 0.12, "gp3": 0.096}
    monkeypatch.setattr(PricingClient, "ebs_storage_price", lambda self, r, t: storage[t])
    monkeypatch.setattr(PricingClient, "gp3_iops_price", lambda self, r: 0.006)
    monkeypatch.setattr(
        PricingClient, "snapshot_price", lambda self, r, archive=False: 0.0125 if archive else 0.05
    )
    monkeypatch.setattr(PricingClient, "idle_ipv4_hourly_price", lambda self, r: 0.005)


def finding_for(check: str, **details) -> Finding:
    return Finding(check=check, resource_id="x", region=REGION, reason="test", details=details)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (100, 2.40),  # 300 IOPS baseline: below gp3's free 3,000
        (1000, 24.00),  # exactly 3,000 IOPS
        (2000, 30.00),  # 48.00 storage saving - 3,000 extra IOPS * 0.006
        (6000, 66.00),  # gp2 capped at 16,000 IOPS: 144.00 - 13,000 * 0.006
    ],
)
def test_gp2_to_gp3_savings(
    pricing: PricingClient, singapore_prices: None, size: int, expected: float
) -> None:
    finding = finding_for("gp2-to-gp3", size_gib=size)
    apply_costs([finding], pricing)
    assert finding.monthly_cost == pytest.approx(expected)


def test_old_snapshot_cost(pricing: PricingClient, singapore_prices: None) -> None:
    standard = finding_for("old-snapshot", size_gib=100, archive=False)
    archived = finding_for("old-snapshot", size_gib=100, archive=True)
    apply_costs([standard, archived], pricing)
    assert standard.monthly_cost == 5.0
    assert archived.monthly_cost == 1.25


def test_unattached_eip_cost(pricing: PricingClient, singapore_prices: None) -> None:
    finding = finding_for("unattached-eip")
    apply_costs([finding], pricing)
    assert finding.monthly_cost == 3.65


@pytest.mark.parametrize(
    ("actual", "wanted", "matches"),
    [
        ("APS1-EBS:SnapshotUsage", "EBS:SnapshotUsage", True),
        ("EBS:SnapshotUsage", "EBS:SnapshotUsage", True),  # us-east-1 has no prefix
        ("APS1-EBS:SnapshotUsage.outposts", "EBS:SnapshotUsage", False),
        ("APS1-LoadBalancerUsage", "LoadBalancerUsage", True),
        ("APS1-TS-LoadBalancerUsage", "LoadBalancerUsage", False),
        ("APS1-Outposts-LoadBalancerUsage", "LoadBalancerUsage", False),
        ("APS1-NatGateway-Hours", "NatGateway-Hours", True),
        ("APS1-RegionalNatGateway-Hours", "NatGateway-Hours", False),
    ],
)
def test_usagetype_matches(actual: str, wanted: str, matches: bool) -> None:
    from cost_waste_finder.pricing import _usagetype_matches

    assert _usagetype_matches(actual, wanted) is matches


def test_load_balancer_price_skips_outposts_and_trust_store(pricing: PricingClient) -> None:
    request = {
        "ServiceCode": "AWSELB",
        "Filters": [
            {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Load Balancer-Application"},
            {"Type": "TERM_MATCH", "Field": "location", "Value": "Asia Pacific (Singapore)"},
        ],
        "MaxResults": 100,
    }
    products = [
        priced_item("APS1-TS-LoadBalancerUsage", "0.0056"),
        priced_item("APS1-Outposts-LoadBalancerUsage", "0.03"),
        priced_item("APS1-LoadBalancerUsage", "0.0252"),
    ]
    with Stubber(pricing._client) as stub:
        stub.add_response("get_products", {"PriceList": products}, request)
        assert pricing.load_balancer_hourly_price(REGION, "application") == pytest.approx(0.0252)


def test_ec2_instance_price_filters(pricing: PricingClient) -> None:
    request = {
        "ServiceCode": "AmazonEC2",
        "Filters": [
            {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Compute Instance"},
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": "t3.micro"},
            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Windows"},
            {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
            {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
            {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
            {"Type": "TERM_MATCH", "Field": "licenseModel", "Value": "No License required"},
            {"Type": "TERM_MATCH", "Field": "location", "Value": "Asia Pacific (Singapore)"},
        ],
        "MaxResults": 100,
    }
    with Stubber(pricing._client) as stub:
        stub.add_response("get_products", {"PriceList": [price_item("0.0224")]}, request)
        price = pricing.ec2_instance_hourly_price(REGION, "t3.micro", "Windows")
        assert price == pytest.approx(0.0224)


@pytest.fixture
def hourly_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real Singapore hourly prices (Oct 2026) without API calls."""
    monkeypatch.setattr(
        PricingClient,
        "ec2_instance_hourly_price",
        lambda self, r, t, os="Linux": {"Linux": 0.0132, "Windows": 0.0224}[os],
    )
    monkeypatch.setattr(PricingClient, "nat_gateway_hourly_price", lambda self, r: 0.059)
    monkeypatch.setattr(
        PricingClient,
        "load_balancer_hourly_price",
        lambda self, r, kind: {"application": 0.0252, "network": 0.0252, "classic": 0.028}[kind],
    )


@pytest.mark.parametrize(
    ("check", "details", "expected"),
    [
        ("idle-ec2", {"instance_type": "t3.micro", "operating_system": "Linux"}, 9.64),
        ("idle-ec2", {"instance_type": "t3.micro", "operating_system": "Windows"}, 16.35),
        ("idle-nat-gateway", {}, 43.07),
        ("idle-load-balancer", {"kind": "application"}, 18.40),
        ("idle-load-balancer", {"kind": "classic"}, 20.44),
    ],
)
def test_hourly_costs(
    pricing: PricingClient, hourly_prices: None, check: str, details: dict, expected: float
) -> None:
    finding = finding_for(check, **details)
    apply_costs([finding], pricing)
    assert finding.monthly_cost == pytest.approx(expected)
