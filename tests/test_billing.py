import json
from datetime import date

import boto3
import pytest
from botocore.stub import Stubber
from click.testing import CliRunner

from cost_waste_finder.billing import (
    USAGE_ONLY,
    build_summary,
    fetch_forecast,
    fetch_monthly_costs,
    get_bill_summary,
    month_start,
    next_month_start,
    percent_change,
    simple_projection,
)
from cost_waste_finder.billing_report import format_change, render_bill_json, render_bill_markdown
from cost_waste_finder.cli import cli

TODAY = date(2026, 10, 7)  # data runs to Oct 6


def ce_client():
    return boto3.client("ce", region_name="us-east-1")


def period(start: str, end: str, services: dict[str, float]) -> dict:
    return {
        "TimePeriod": {"Start": start, "End": end},
        "Total": {},
        "Groups": [
            {"Keys": [name], "Metrics": {"UnblendedCost": {"Amount": str(amount), "Unit": "USD"}}}
            for name, amount in services.items()
        ],
        "Estimated": False,
    }


def usage_request(start: str, end: str, token: str | None = None) -> dict:
    request = {
        "TimePeriod": {"Start": start, "End": end},
        "Granularity": "MONTHLY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        "Filter": USAGE_ONLY,
    }
    if token:
        request["NextPageToken"] = token
    return request


def forecast_request(start: str, end: str) -> dict:
    return {
        "TimePeriod": {"Start": start, "End": end},
        "Granularity": "MONTHLY",
        "Metric": "UNBLENDED_COST",
        "Filter": USAGE_ONLY,
    }


AUG = {"Amazon Elastic Compute Cloud - Compute": 800.0, "Amazon RDS": 300.0, "AWS KMS": 0.4}
SEP = {"Amazon Elastic Compute Cloud - Compute": 920.4, "Amazon RDS": 264.9, "AWS KMS": 0.5}
OCT = {"Amazon Elastic Compute Cloud - Compute": 180.0, "Amazon RDS": 54.0, "AWS KMS": 0.1}


# --- dates -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("today", "back", "expected"),
    [
        (date(2026, 10, 7), 2, date(2026, 8, 1)),
        (date(2026, 2, 15), 2, date(2025, 12, 1)),  # across the new year
        (date(2026, 1, 1), 1, date(2025, 12, 1)),
    ],
)
def test_month_start(today: date, back: int, expected: date) -> None:
    assert month_start(today, back) == expected


def test_next_month_start() -> None:
    assert next_month_start(date(2026, 10, 31)) == date(2026, 11, 1)
    assert next_month_start(date(2026, 12, 7)) == date(2027, 1, 1)


def test_simple_projection() -> None:
    assert simple_projection(60.0, date(2026, 10, 7)) == 310.0  # 6 days -> 31 days
    assert simple_projection(0.0, date(2026, 10, 1)) is None  # no full day yet


def test_percent_change() -> None:
    assert percent_change(100, 115.3) == 15.3
    assert percent_change(0, 50) is None


def test_format_change() -> None:
    assert format_change(1204.10, 1388.55) == "▲ $184.45 (+15.3%)"
    assert format_change(1388.55, 1310.00) == "▼ $78.55 (-5.7%)"
    assert format_change(0, 12) == "▲ $12.00 (new)"
    assert format_change(5, 5) == "-"


# --- Cost Explorer calls ---------------------------------------------------------------------


def test_fetch_follows_pages_and_counts_calls() -> None:
    ce = ce_client()
    with Stubber(ce) as stub:
        stub.add_response(
            "get_cost_and_usage",
            {"ResultsByTime": [period("2026-08-01", "2026-09-01", AUG)], "NextPageToken": "p2"},
            usage_request("2026-08-01", "2026-10-07"),
        )
        stub.add_response(
            "get_cost_and_usage",
            {
                "ResultsByTime": [
                    period("2026-09-01", "2026-10-01", SEP),
                    period("2026-10-01", "2026-10-07", OCT),
                ]
            },
            usage_request("2026-08-01", "2026-10-07", token="p2"),
        )
        costs, calls = fetch_monthly_costs(ce, date(2026, 8, 1), TODAY)

    assert calls == 2
    assert costs[date(2026, 9, 1)]["Amazon RDS"] == 264.9
    assert costs[date(2026, 10, 1)]["AWS KMS"] == 0.1


def test_forecast() -> None:
    ce = ce_client()
    with Stubber(ce) as stub:
        stub.add_response(
            "get_cost_forecast",
            {"Total": {"Amount": "1000.5", "Unit": "USD"}},
            forecast_request("2026-10-07", "2026-11-01"),
        )
        assert fetch_forecast(ce, TODAY) == (1000.5, 1)


def test_forecast_unavailable() -> None:
    ce = ce_client()
    with Stubber(ce) as stub:
        stub.add_client_error("get_cost_forecast", "DataUnavailableException")
        assert fetch_forecast(ce, TODAY) == (None, 1)


# --- summary ---------------------------------------------------------------------------------


def costs() -> dict:
    return {date(2026, 8, 1): AUG, date(2026, 9, 1): SEP, date(2026, 10, 1): OCT}


def test_summary_months_with_aws_forecast() -> None:
    summary = build_summary(costs(), forecast=1000.0, today=TODAY, api_calls=2)

    aug, sep, oct_ = summary.months
    assert (aug.label, aug.total) == ("Aug 2026", 1100.4)
    assert (sep.label, sep.total) == ("Sep 2026", 1185.8)
    assert oct_.partial and oct_.total == 234.1
    assert oct_.projected == 1234.1
    assert oct_.projection_method == "AWS forecast"


def test_summary_falls_back_to_simple_projection() -> None:
    summary = build_summary(costs(), forecast=None, today=TODAY, api_calls=2)

    assert summary.months[2].projected == round(234.1 / 6 * 31, 2)
    assert summary.months[2].projection_method == "simple projection"


def test_services_sorted_and_small_ones_grouped() -> None:
    summary = build_summary(costs(), forecast=None, today=TODAY, api_calls=2)

    names = [t.service for t in summary.services]
    assert names == ["Amazon Elastic Compute Cloud - Compute", "Amazon RDS", "Other"]
    ec2 = summary.services[0]
    assert ec2.change == 120.4
    assert ec2.current_projected == 930.0  # 180 / 6 days * 31
    other = summary.services[2]
    assert (other.month_2, other.month_1, other.current_so_far) == (0.4, 0.5, 0.1)


def test_first_day_of_month() -> None:
    today = date(2026, 10, 1)  # nothing billed for October yet
    summary = build_summary(
        {date(2026, 8, 1): AUG, date(2026, 9, 1): SEP}, forecast=1200.0, today=today, api_calls=2
    )

    assert summary.months[2].total == 0
    assert summary.months[2].projected == 1200.0


# --- reports and CLI -------------------------------------------------------------------------


def test_markdown_report() -> None:
    report = render_bill_markdown(build_summary(costs(), 1000.0, TODAY, 2))

    assert "| Aug 2026 | $1,100.40 | |" in report
    assert "| Sep 2026 | $1,185.80 | ▲ $85.40 (+7.8%) |" in report
    assert "| Oct 2026 (so far, to Oct 6) | $234.10 | |" in report
    assert "| Oct 2026 (projected, AWS forecast) | $1,234.10 | ▲ $48.30 (+4.1%) |" in report
    assert "## Biggest increases (Sep vs Aug)" in report
    assert "| Amazon RDS | ▼ $35.10 (-11.7%) |" in report


def test_json_report() -> None:
    data = json.loads(render_bill_json(build_summary(costs(), 1000.0, TODAY, 2)))

    assert data["cost_explorer_calls"] == 2
    assert [m["month"] for m in data["months"]] == ["2026-08", "2026-09", "2026-10"]
    assert data["months"][2]["projected"] == 1234.1
    assert data["biggest_increases"] == ["Amazon Elastic Compute Cloud - Compute"]
    assert data["biggest_decreases"] == ["Amazon RDS"]


def test_get_bill_summary_uses_us_east_1(monkeypatch: pytest.MonkeyPatch) -> None:
    regions = []

    class FakeSession:
        def client(self, service, region_name):
            regions.append((service, region_name))
            return ce_client()

    monkeypatch.setattr(
        "cost_waste_finder.billing.fetch_monthly_costs", lambda ce, start, end: (costs(), 1)
    )
    monkeypatch.setattr("cost_waste_finder.billing.fetch_forecast", lambda ce, today: (None, 1))

    summary = get_bill_summary(FakeSession(), today=TODAY)

    assert regions == [("ce", "us-east-1")]
    assert summary.api_calls == 2


def test_cli_bill_prints_report_and_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cost_waste_finder.cli.get_bill_summary",
        lambda session: build_summary(costs(), 1000.0, TODAY, 2),
    )

    result = CliRunner().invoke(cli, ["bill"])

    assert result.exit_code == 0, result.output
    assert "# AWS bill trend" in result.stdout
    assert "Cost Explorer calls: 2 (~$0.02)" in result.stderr


def test_cli_bill_json_to_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        "cost_waste_finder.cli.get_bill_summary",
        lambda session: build_summary(costs(), 1000.0, TODAY, 2),
    )
    target = tmp_path / "reports" / "bill.json"

    result = CliRunner().invoke(cli, ["bill", "--format", "json", "--output", str(target)])

    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text())["as_of"] == "2026-10-07"


def test_cli_bill_explains_access_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    from botocore.exceptions import ClientError

    def denied(session):
        raise ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "not enabled"}},
            "GetCostAndUsage",
        )

    monkeypatch.setattr("cost_waste_finder.cli.get_bill_summary", denied)
    result = CliRunner().invoke(cli, ["bill"])

    assert result.exit_code != 0
    assert "Cost Explorer error: AccessDeniedException: not enabled" in result.output
    assert "Traceback" not in result.output
