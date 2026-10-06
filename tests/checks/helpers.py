"""Shared helpers for the CloudWatch-based check tests."""

from datetime import UTC, datetime, timedelta

REGION = "ap-southeast-1"
MB = 1024**2
GB = 1024**3


def days_later(days: int) -> datetime:
    """moto stamps resources with the current time, so we move "now" forward instead."""
    return datetime.now(UTC) + timedelta(days=days)


def put_daily(
    cloudwatch,
    namespace: str,
    metric: str,
    dimensions: dict[str, str],
    value: float,
    now: datetime,
    days: int = 14,
) -> None:
    """Put one data point per day for the `days` days before `now`."""
    for day in range(days):
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    "MetricName": metric,
                    "Dimensions": [{"Name": k, "Value": v} for k, v in dimensions.items()],
                    "Timestamp": now - timedelta(days=day, hours=1),
                    "Value": value,
                }
            ],
        )
