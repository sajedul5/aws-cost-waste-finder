"""Small read-only CloudWatch helper used by the idle checks."""

from datetime import datetime, timedelta

SECONDS_PER_DAY = 86_400


def daily_values(
    cloudwatch,
    namespace: str,
    metric: str,
    dimensions: dict[str, str],
    statistic: str,
    days: int,
    now: datetime,
) -> list[float]:
    """One value per day (Average or Sum) for the last `days` days. Empty if there is no data."""
    response = cloudwatch.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric,
        Dimensions=[{"Name": name, "Value": value} for name, value in dimensions.items()],
        StartTime=now - timedelta(days=days),
        EndTime=now,
        Period=SECONDS_PER_DAY,
        Statistics=[statistic],
    )
    return [point[statistic] for point in response["Datapoints"]]


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None
