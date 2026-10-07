"""The IAM policy must allow every AWS call the code makes, and nothing that writes."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import boto3
from moto import mock_aws

from cost_waste_finder.billing import get_bill_summary
from cost_waste_finder.checks import idle_load_balancers, idle_nat_gateways, stopped_ec2
from cost_waste_finder.config import Thresholds
from cost_waste_finder.scanner import enabled_regions, scan_regions

POLICY = Path(__file__).parent.parent / "iam" / "read-only-policy.json"
REGION = "ap-southeast-1"

# boto3 client name -> IAM action prefix
IAM_PREFIX = {
    "ec2": "ec2",
    "cloudwatch": "cloudwatch",
    "elbv2": "elasticloadbalancing",
    "elb": "elasticloadbalancing",
    "pricing": "pricing",
    "ce": "ce",
}

PRICE_ITEM = json.dumps(
    {
        "product": {"attributes": {"usagetype": "APS1-LoadBalancerUsage"}},
        "terms": {"OnDemand": {"T": {"priceDimensions": {"D": {"pricePerUnit": {"USD": "0.1"}}}}}},
    }
)


def policy_actions() -> set[str]:
    policy = json.loads(POLICY.read_text())
    return {action for statement in policy["Statement"] for action in statement["Action"]}


def build_account(session: boto3.Session) -> None:
    """One of everything, so every check's code path makes its API calls."""
    ec2 = session.client("ec2")
    image_id = ec2.describe_images()["Images"][0]["ImageId"]
    running = ec2.run_instances(ImageId=image_id, MinCount=1, MaxCount=1)["Instances"][0]
    stopped = ec2.run_instances(ImageId=image_id, MinCount=1, MaxCount=1)["Instances"][0]
    ec2.stop_instances(InstanceIds=[stopped["InstanceId"]])
    volume_id = ec2.create_volume(AvailabilityZone=f"{REGION}a", Size=10)["VolumeId"]
    ec2.create_snapshot(VolumeId=volume_id)
    ec2.allocate_address(Domain="vpc")
    subnets = [s["SubnetId"] for s in ec2.describe_subnets()["Subnets"]][:2]
    ec2.create_nat_gateway(
        SubnetId=subnets[0], AllocationId=ec2.allocate_address(Domain="vpc")["AllocationId"]
    )

    elbv2 = session.client("elbv2")
    lb = elbv2.create_load_balancer(Name="test-alb", Subnets=subnets)["LoadBalancers"][0]
    group_arn = elbv2.create_target_group(
        Name="test-tg", Protocol="HTTP", Port=80, VpcId=lb["VpcId"]
    )["TargetGroups"][0]["TargetGroupArn"]
    elbv2.register_targets(TargetGroupArn=group_arn, Targets=[{"Id": running["InstanceId"]}])
    elbv2.create_listener(
        LoadBalancerArn=lb["LoadBalancerArn"],
        Protocol="HTTP",
        Port=80,
        DefaultActions=[{"Type": "forward", "TargetGroupArn": group_arn}],
    )
    session.client("elb").create_load_balancer(
        LoadBalancerName="test-clb",
        Listeners=[{"Protocol": "HTTP", "LoadBalancerPort": 80, "InstancePort": 80}],
        AvailabilityZones=[f"{REGION}a"],
    )


@mock_aws
def test_policy_covers_every_api_call() -> None:
    session = boto3.Session(region_name=REGION)
    build_account(session)
    called: set[str] = set()

    def record(model, **kwargs):
        called.add(f"{IAM_PREFIX[model.service_model.service_name]}:{model.name}")

    def fake_pricing(model, **kwargs):
        # moto has no Pricing API: answer GetProducts locally instead of calling AWS.
        # Answering stops the other before-call handlers, so record the call here too.
        record(model)
        return SimpleNamespace(status_code=200, headers={}), {"PriceList": [PRICE_ITEM]}

    def fake_cost_explorer(model, **kwargs):
        # Never call real Cost Explorer (it charges per call): answer locally.
        record(model)
        body = (
            {"ResultsByTime": []}
            if model.name == "GetCostAndUsage"
            else {"Total": {"Amount": "1", "Unit": "USD"}}
        )
        return SimpleNamespace(status_code=200, headers={}), body

    session.events.register("before-call", record)
    session.events.register("before-call.pricing.GetProducts", fake_pricing)
    session.events.register("before-call.ce", fake_cost_explorer)

    enabled_regions(session, REGION)
    findings = scan_regions(session, [REGION])
    # moto resources are brand new, so the time-gated checks skip them in a normal scan.
    # Run those again a few days "later" so their remaining calls are made too.
    later = datetime.now(UTC) + timedelta(days=3)
    short = Thresholds(lookback_days=1, stopped_days=1)
    for check in (idle_load_balancers.check, idle_nat_gateways.check, stopped_ec2.check):
        check(session, REGION, short, now=later)

    get_bill_summary(session)  # cwf bill

    assert findings, "the fake account should produce findings"
    expected_calls = {
        "ec2:DescribeVolumes",
        "ec2:DescribeSnapshots",
        "ec2:DescribeImages",
        "ec2:DescribeAddresses",
        "ec2:DescribeInstances",
        "ec2:DescribeNatGateways",
        "ec2:DescribeRegions",
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeTargetGroups",
        "elasticloadbalancing:DescribeTargetHealth",
        "cloudwatch:GetMetricStatistics",
        "pricing:GetProducts",
        "ce:GetCostAndUsage",
        "ce:GetCostForecast",
    }
    assert expected_calls <= called, f"code paths not exercised: {expected_calls - called}"
    missing = called - policy_actions()
    assert not missing, f"add these to iam/read-only-policy.json: {sorted(missing)}"


def test_policy_is_read_only() -> None:
    for action in policy_actions():
        operation = action.split(":", 1)[1]
        assert operation.startswith(("Describe", "Get", "List")), action


def test_policy_has_no_account_ids() -> None:
    text = POLICY.read_text() + (POLICY.parent / "trust-policy.example.json").read_text()
    assert not any(part.isdigit() and len(part) == 12 for part in text.replace(":", " ").split())
