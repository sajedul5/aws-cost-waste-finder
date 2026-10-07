"""3-month bill trend from Cost Explorer. Opt-in only (`cwf bill`): ~$0.01 per API call."""

import calendar
from collections import defaultdict
from datetime import date, timedelta

import boto3

from cost_waste_finder.models import BillSummary, MonthCost, ServiceTrend

# Cost Explorer is a global service served from us-east-1.
COST_EXPLORER_REGION = "us-east-1"
COST_PER_CALL_USD = 0.01
OTHER_THRESHOLD_USD = 1.0  # services below this in every month are grouped as "Other"

# Show usage, not credits or refunds, so the trend is about what was actually used.
USAGE_ONLY = {"Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Refund"]}}}


def month_start(day: date, months_back: int = 0) -> date:
    year, month = day.year, day.month - months_back
    while month < 1:
        year, month = year - 1, month + 12
    return date(year, month, 1)


def next_month_start(day: date) -> date:
    return (day.replace(day=1) + timedelta(days=32)).replace(day=1)


def get_bill_summary(session: boto3.Session, today: date | None = None) -> BillSummary:
    """Month before last, last month and the current month (so far + forecast), per service."""
    today = today or date.today()
    ce = session.client("ce", region_name=COST_EXPLORER_REGION)
    costs, calls = fetch_monthly_costs(ce, month_start(today, 2), today)
    forecast, forecast_calls = fetch_forecast(ce, today)
    return build_summary(costs, forecast, today, calls + forecast_calls)


def fetch_monthly_costs(ce, start: date, end: date) -> tuple[dict[date, dict[str, float]], int]:
    """{month start: {service: USD}} for [start, end). Returns the number of API calls too."""
    costs: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    params = {
        "TimePeriod": {"Start": start.isoformat(), "End": end.isoformat()},
        "Granularity": "MONTHLY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        "Filter": USAGE_ONLY,
    }
    calls = 0
    while True:
        response = ce.get_cost_and_usage(**params)
        calls += 1
        for period in response["ResultsByTime"]:
            month = date.fromisoformat(period["TimePeriod"]["Start"]).replace(day=1)
            for group in period["Groups"]:
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                costs[month][group["Keys"][0]] += amount
        token = response.get("NextPageToken")
        if not token:
            return costs, calls
        params["NextPageToken"] = token


def fetch_forecast(ce, today: date) -> tuple[float | None, int]:
    """AWS forecast for today until the end of the month, or None if AWS can't forecast yet."""
    try:
        response = ce.get_cost_forecast(
            TimePeriod={"Start": today.isoformat(), "End": next_month_start(today).isoformat()},
            Granularity="MONTHLY",
            Metric="UNBLENDED_COST",
            Filter=USAGE_ONLY,
        )
    except ce.exceptions.DataUnavailableException:
        return None, 1  # e.g. a new account with too little history
    return float(response["Total"]["Amount"]), 1


def simple_projection(so_far: float, today: date) -> float | None:
    """Scale the cost so far (to yesterday) to the whole month."""
    days_elapsed = today.day - 1
    if days_elapsed == 0:
        return None
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return round(so_far / days_elapsed * days_in_month, 2)


def build_summary(
    costs: dict[date, dict[str, float]], forecast: float | None, today: date, api_calls: int
) -> BillSummary:
    m2, m1, current = month_start(today, 2), month_start(today, 1), month_start(today)

    def total(month: date) -> float:
        return round(sum(costs.get(month, {}).values()), 2)

    so_far = total(current)
    if forecast is not None:
        projected, method = round(so_far + forecast, 2), "AWS forecast"
    else:
        projected, method = simple_projection(so_far, today), "simple projection"
    months = [
        MonthCost(m2, total(m2)),
        MonthCost(m1, total(m1)),
        MonthCost(current, so_far, partial=True, projected=projected, projection_method=method),
    ]
    return BillSummary(today, months, service_trends(costs, m2, m1, current, today), api_calls)


def service_trends(
    costs: dict[date, dict[str, float]], m2: date, m1: date, current: date, today: date
) -> list[ServiceTrend]:
    """One trend per service, biggest last month first; tiny services combined as "Other"."""
    names = {name for month in (m2, m1, current) for name in costs.get(month, {})}
    big, small = [], []
    for name in sorted(names):
        values = [round(costs.get(month, {}).get(name, 0.0), 2) for month in (m2, m1, current)]
        trend = ServiceTrend(name, *values, simple_projection(values[2], today))
        largest = max(values[0], values[1], trend.current_projected or values[2])
        (small if largest < OTHER_THRESHOLD_USD else big).append(trend)
    big.sort(key=lambda t: -t.month_1)
    if any(t.month_2 or t.month_1 or t.current_so_far for t in small):
        big.append(combine("Other", small))
    return big


def combine(name: str, trends: list[ServiceTrend]) -> ServiceTrend:
    projected = [t.current_projected for t in trends if t.current_projected is not None]
    return ServiceTrend(
        name,
        round(sum(t.month_2 for t in trends), 2),
        round(sum(t.month_1 for t in trends), 2),
        round(sum(t.current_so_far for t in trends), 2),
        round(sum(projected), 2) if projected else None,
    )


def percent_change(before: float, after: float) -> float | None:
    """None when there is nothing to compare against (before is $0)."""
    if before == 0:
        return None
    return round((after - before) / before * 100, 1)
