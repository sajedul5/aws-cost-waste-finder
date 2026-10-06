"""Check: load balancers with no targets, or almost no traffic over the lookback period."""

from datetime import UTC, datetime, timedelta

import boto3

from cost_waste_finder.config import Thresholds
from cost_waste_finder.metrics import daily_values
from cost_waste_finder.models import Finding

CHECK_ID = "idle-load-balancer"

# kind -> (CloudWatch namespace, traffic metric, label in the report)
TRAFFIC_METRICS = {
    "application": ("AWS/ApplicationELB", "RequestCount", "ALB", "requests"),
    "network": ("AWS/NetworkELB", "NewFlowCount", "NLB", "new flows"),
    "classic": ("AWS/ELB", "RequestCount", "Classic ELB", "requests"),
}


def check(
    session: boto3.Session, region: str, thresholds: Thresholds, now: datetime | None = None
) -> list[Finding]:
    now = now or datetime.now(UTC)
    created_before = now - timedelta(days=thresholds.lookback_days)  # newer: not enough history
    cloudwatch = session.client("cloudwatch", region_name=region)
    findings = []
    for kind, name, dimension, has_targets in _load_balancers(session, region, created_before):
        reason = _idle_reason(cloudwatch, kind, dimension, has_targets, thresholds, now)
        if reason:
            findings.append(
                Finding(
                    check=CHECK_ID,
                    resource_id=name,
                    region=region,
                    reason=reason,
                    details={"kind": kind},
                )
            )
    return findings


def _load_balancers(session: boto3.Session, region: str, created_before: datetime):
    """Yield (kind, report name, CloudWatch dimension, has targets) for older load balancers."""
    elbv2 = session.client("elbv2", region_name=region)
    for page in elbv2.get_paginator("describe_load_balancers").paginate():
        for lb in page["LoadBalancers"]:
            kind = lb["Type"]
            if kind not in ("application", "network") or lb["CreatedTime"] > created_before:
                continue  # gateway LBs are out of scope; new LBs lack history
            # "app/my-alb/123abc": the CloudWatch dimension, and a readable ID without the ARN.
            short_id = lb["LoadBalancerArn"].split(":loadbalancer/", 1)[1]
            yield kind, short_id, short_id, _has_targets(elbv2, lb)

    elb = session.client("elb", region_name=region)
    for page in elb.get_paginator("describe_load_balancers").paginate():
        for lb in page["LoadBalancerDescriptions"]:
            if lb["CreatedTime"] > created_before:
                continue
            name = lb["LoadBalancerName"]
            yield "classic", name, name, bool(lb.get("Instances"))


def _has_targets(elbv2, lb: dict) -> bool:
    try:
        groups = elbv2.describe_target_groups(LoadBalancerArn=lb["LoadBalancerArn"])
    except elbv2.exceptions.TargetGroupNotFoundException:
        return False  # no target groups at all
    for group in groups["TargetGroups"]:
        health = elbv2.describe_target_health(TargetGroupArn=group["TargetGroupArn"])
        if health["TargetHealthDescriptions"]:
            return True
    return False


def _idle_reason(
    cloudwatch, kind: str, dimension: str, has_targets: bool, thresholds: Thresholds, now
) -> str | None:
    namespace, metric, label, unit = TRAFFIC_METRICS[kind]
    if not has_targets:
        return f"{label} with no registered targets"
    dimension_name = "LoadBalancerName" if kind == "classic" else "LoadBalancer"
    days = thresholds.lookback_days
    traffic = sum(
        daily_values(cloudwatch, namespace, metric, {dimension_name: dimension}, "Sum", days, now)
    )
    if traffic >= thresholds.lb_requests:
        return None
    return f"{label} with {traffic:.0f} {unit} in {days} days"
