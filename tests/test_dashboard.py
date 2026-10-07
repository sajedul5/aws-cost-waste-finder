import re
from datetime import date
from html import escape

import pytest
from click.testing import CliRunner

from cost_waste_finder.billing import build_summary
from cost_waste_finder.cli import cli
from cost_waste_finder.dashboard import (
    ACTIONS,
    bar_heights,
    bill_chart_svg,
    render_dashboard,
    savings_share,
)
from cost_waste_finder.models import Finding

DAY = date(2026, 10, 7)
REGIONS = ["ap-southeast-1", "ap-southeast-2"]


def bill():
    costs = {
        date(2026, 8, 1): {"Amazon EC2": 800.0, "Amazon RDS": 300.0},
        date(2026, 9, 1): {"Amazon EC2": 920.4, "Amazon RDS": 264.9},
        date(2026, 10, 1): {"Amazon EC2": 180.0, "Amazon RDS": 54.0},
    }
    return build_summary(costs, forecast=1000.0, today=DAY, api_calls=2)


def findings() -> list[Finding]:
    return [
        Finding("idle-nat-gateway", "nat-0ccc3333dddd4444e", "ap-southeast-1", "idle", {}, 43.07),
        Finding("stopped-ec2", "i-0bbb7777cccc8888d", "ap-southeast-2", "stopped", {}, 28.80),
        Finding("old-snapshot", "snap-0ddd9999eeee0000f", "ap-southeast-1", "old", {}, 4.04),
        Finding("unattached-eip", "eipalloc-0f1e2d3c", "ap-southeast-1", "unused", {}, None),
    ]


def test_kpis() -> None:
    page = render_dashboard(findings(), REGIONS, bill(), "Client A", DAY)

    assert "<title>Client A · AWS cost dashboard</title>" in page
    assert "Oct 2026 (projected)" in page
    assert "$1,234.00" in page  # so far 234.00 + forecast 1000
    assert "Sep 2026 bill" in page and "$1,185.30" in page
    assert "$75.91/mo" in page  # potential savings
    assert "6.4%" in page  # 75.91 / 1185.30


def test_cost_increase_is_red_and_decrease_green() -> None:
    page = render_dashboard(findings(), REGIONS, bill(), None, DAY)

    assert '<span class="up">▲ $85.30 (+7.8%)</span> vs Aug' in page  # Sep vs Aug went up
    assert '<span class="down">▼ $35.10 (-11.7%)</span>' in page  # RDS went down


def test_sections_and_actions() -> None:
    page = render_dashboard(findings(), REGIONS, bill(), None, DAY)

    for heading in ("Bill: last 3 months", "Top services", "Top findings", "Recommended actions"):
        assert heading in page
    actions = page[page.index("Recommended actions") :]
    assert actions.index("nat-0ccc3333dddd4444e") < actions.index("i-0bbb7777cccc8888d")
    assert escape(ACTIONS["idle-nat-gateway"]) in actions
    assert "eipalloc-0f1e2d3c" not in actions  # no price, so not a top action


def test_without_bill() -> None:
    page = render_dashboard(findings(), REGIONS, None, None, DAY)

    assert "Not included" in page
    assert "Bill: last 3 months" not in page
    assert "Cost Explorer" not in page


def test_empty_account() -> None:
    page = render_dashboard([], REGIONS, None, None, DAY)

    assert "No waste found." in page
    assert "Recommended actions" not in page


def test_bar_heights() -> None:
    assert bar_heights([50, 100, 25], 150) == [75.0, 150.0, 37.5]
    assert bar_heights([0, 0, 0], 150) == [0.0, 0.0, 0.0]


def test_chart_has_hatched_projection() -> None:
    svg = bill_chart_svg(bill())

    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert 'fill="url(#hatch)"' in svg
    assert "Oct 2026 (proj.)" in svg
    assert 'height="-' not in svg  # no negative bars


def test_chart_with_zero_bill() -> None:
    zero = build_summary({}, forecast=None, today=DAY, api_calls=2)
    assert "<svg" in bill_chart_svg(zero)


def test_savings_share() -> None:
    assert savings_share(findings(), bill()) == 6.4
    assert savings_share(findings(), None) is None


def test_escapes_and_no_external_resources() -> None:
    bad = Finding("idle-load-balancer", "<b>x</b>", "ap-southeast-1", "<script>x</script>", {}, 1)
    page = render_dashboard([bad], REGIONS, bill(), '<img src="x">', DAY)

    assert "<script" not in page
    assert "<img" not in page
    assert "&lt;script&gt;" in page
    assert not re.search(r"https?://", page)
    assert "<link" not in page


def test_cli_dashboard_writes_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    seen = {}

    def fake_scan(session, regions, thresholds):
        seen["regions"] = regions
        return findings()

    monkeypatch.setattr("cost_waste_finder.cli.scan_regions", fake_scan)
    monkeypatch.setattr("cost_waste_finder.cli.enabled_regions", lambda s, r: REGIONS)
    monkeypatch.setattr("cost_waste_finder.cli.get_bill_summary", lambda session: bill())
    target = tmp_path / "reports" / "dashboard.html"

    result = CliRunner().invoke(cli, ["dashboard", "--output", str(target), "--title", "Client A"])

    assert result.exit_code == 0, result.output
    assert seen["regions"] == REGIONS  # all regions by default
    assert "Cost Explorer calls: 2 (~$0.02)" in result.stderr
    assert "Client A · AWS cost dashboard" in target.read_text()


def test_cli_dashboard_no_bill_and_single_region(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    def no_cost_explorer(session):
        raise AssertionError("Cost Explorer must not be called with --no-bill")

    monkeypatch.setattr("cost_waste_finder.cli.scan_regions", lambda s, r, t: findings())
    monkeypatch.setattr("cost_waste_finder.cli.get_bill_summary", no_cost_explorer)
    target = tmp_path / "d.html"

    result = CliRunner().invoke(
        cli, ["dashboard", "--output", str(target), "--no-bill", "--region", "ap-southeast-1"]
    )

    assert result.exit_code == 0, result.output
    assert "Region: ap-southeast-1" in target.read_text()
    assert "Cost Explorer" not in result.stderr


def test_cli_dashboard_needs_output() -> None:
    result = CliRunner().invoke(cli, ["dashboard"])
    assert result.exit_code != 0
    assert "--output" in result.output
