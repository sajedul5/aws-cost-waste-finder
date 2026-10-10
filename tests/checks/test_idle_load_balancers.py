import boto3
from helpers import REGION, days_later, put_daily
from moto import mock_aws

from cost_waste_finder.checks import CHECKS, idle_load_balancers
from cost_waste_finder.config import Thresholds

LATER = days_later(15)


def create_lb(session: boto3.Session, name: str, kind: str = "application") -> dict:
    ec2 = session.client("ec2")
    subnets = [s["SubnetId"] for s in ec2.describe_subnets()["Subnets"]][:2]
    elbv2 = session.client("elbv2")
    return elbv2.create_load_balancer(Name=name, Subnets=subnets, Type=kind)["LoadBalancers"][0]


def add_target(session: boto3.Session, lb: dict) -> None:
    """Register one instance behind the load balancer through a listener."""
    ec2 = session.client("ec2")
    elbv2 = session.client("elbv2")
    image_id = ec2.describe_images()["Images"][0]["ImageId"]
    instance_id = ec2.run_instances(ImageId=image_id, MinCount=1, MaxCount=1)["Instances"][0][
        "InstanceId"
    ]
    protocol = "HTTP" if lb["Type"] == "application" else "TCP"
    group_arn = elbv2.create_target_group(
        Name=f"{lb['LoadBalancerName']}-tg", Protocol=protocol, Port=80, VpcId=lb["VpcId"]
    )["TargetGroups"][0]["TargetGroupArn"]
    elbv2.register_targets(TargetGroupArn=group_arn, Targets=[{"Id": instance_id}])
    elbv2.create_listener(
        LoadBalancerArn=lb["LoadBalancerArn"],
        Protocol=protocol,
        Port=80,
        DefaultActions=[{"Type": "forward", "TargetGroupArn": group_arn}],
    )


def short_id(lb: dict) -> str:
    return lb["LoadBalancerArn"].split(":loadbalancer/", 1)[1]


def put_requests(session: boto3.Session, lb: dict, per_day: float) -> None:
    namespace, metric = (
        ("AWS/ApplicationELB", "RequestCount")
        if lb["Type"] == "application"
        else ("AWS/NetworkELB", "NewFlowCount")
    )
    put_daily(
        session.client("cloudwatch"),
        namespace,
        metric,
        {"LoadBalancer": short_id(lb)},
        per_day,
        LATER,
    )


def run(session: boto3.Session, **thresholds) -> dict:
    findings = idle_load_balancers.check(session, REGION, Thresholds(**thresholds), now=LATER)
    return {f.resource_id: f for f in findings}


@mock_aws
def test_alb_without_targets_is_idle() -> None:
    session = boto3.Session(region_name=REGION)
    lb = create_lb(session, "empty-alb")

    findings = run(session)

    finding = findings[short_id(lb)]
    assert finding.check == "idle-load-balancer"
    assert finding.reason == "ALB with no registered targets and 0 requests in 14 days"
    assert finding.details == {"kind": "application"}
    assert short_id(lb).startswith("app/empty-alb/")  # readable ID, no ARN or account ID


@mock_aws
def test_busy_alb_without_targets_is_not_idle() -> None:
    """e.g. an ALB that only redirects HTTP -> HTTPS: no targets, but still in use."""
    session = boto3.Session(region_name=REGION)
    lb = create_lb(session, "redirect-alb")
    put_requests(session, lb, per_day=1000)

    assert short_id(lb) not in run(session)


@mock_aws
def test_alb_with_targets_but_few_requests_is_idle() -> None:
    session = boto3.Session(region_name=REGION)
    lb = create_lb(session, "quiet-alb")
    add_target(session, lb)
    put_requests(session, lb, per_day=1)

    findings = run(session)

    assert findings[short_id(lb)].reason == "ALB with 14 requests in 14 days"


@mock_aws
def test_busy_alb_is_not_idle() -> None:
    session = boto3.Session(region_name=REGION)
    lb = create_lb(session, "busy-alb")
    add_target(session, lb)
    put_requests(session, lb, per_day=1000)

    assert short_id(lb) not in run(session)
    assert short_id(lb) in run(session, lb_requests=1_000_000)


@mock_aws
def test_nlb_without_targets_is_idle() -> None:
    session = boto3.Session(region_name=REGION)
    lb = create_lb(session, "empty-nlb", kind="network")

    finding = run(session)[short_id(lb)]

    assert finding.reason == "NLB with no registered targets and 0 new flows in 14 days"
    assert finding.details == {"kind": "network"}


@mock_aws
def test_classic_elb() -> None:
    session = boto3.Session(region_name=REGION)
    elb = session.client("elb")
    listeners = [{"Protocol": "HTTP", "LoadBalancerPort": 80, "InstancePort": 80}]
    for name in ("empty-clb", "busy-clb"):
        elb.create_load_balancer(
            LoadBalancerName=name, Listeners=listeners, AvailabilityZones=[f"{REGION}a"]
        )
    ec2 = session.client("ec2")
    image_id = ec2.describe_images()["Images"][0]["ImageId"]
    instance_id = ec2.run_instances(ImageId=image_id, MinCount=1, MaxCount=1)["Instances"][0][
        "InstanceId"
    ]
    elb.register_instances_with_load_balancer(
        LoadBalancerName="busy-clb", Instances=[{"InstanceId": instance_id}]
    )
    put_daily(
        session.client("cloudwatch"),
        "AWS/ELB",
        "RequestCount",
        {"LoadBalancerName": "busy-clb"},
        1000,
        LATER,
    )

    findings = run(session)

    assert (
        findings["empty-clb"].reason
        == "Classic ELB with no registered targets and 0 requests in 14 days"
    )
    assert findings["empty-clb"].details == {"kind": "classic"}
    assert "busy-clb" not in findings


@mock_aws
def test_skips_new_load_balancer() -> None:
    session = boto3.Session(region_name=REGION)
    create_lb(session, "new-alb")

    findings = idle_load_balancers.check(session, REGION, Thresholds(), now=days_later(5))

    assert findings == []


def test_check_is_registered() -> None:
    assert idle_load_balancers.check in CHECKS
