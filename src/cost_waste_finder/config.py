"""Thresholds that decide when a resource counts as waste. All are CLI options."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    lookback_days: int = 14  # CloudWatch history used by the idle checks
    cpu_percent: float = 5.0  # idle EC2: average CPU below this ...
    network_mb_per_day: float = 5.0  # ... and network in + out below this
    nat_gb: float = 1.0  # idle NAT Gateway: total GB sent over the lookback
    lb_requests: int = 100  # idle load balancer: total requests/new flows over the lookback
    snapshot_age_days: int = 90  # old snapshot: older than this
    stopped_days: int = 30  # stopped EC2: stopped longer than this
