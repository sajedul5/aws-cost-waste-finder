from datetime import date

from cost_waste_finder.models import Finding
from cost_waste_finder.report import render_markdown, sort_by_savings, total_savings

REGION = "ap-southeast-1"
DAY = date(2026, 1, 15)


def finding(resource_id: str, cost: float | None, reason: str = "test") -> Finding:
    return Finding(
        check="unattached-ebs",
        resource_id=resource_id,
        region=REGION,
        reason=reason,
        monthly_cost=cost,
    )


def test_sort_highest_first_unpriced_last() -> None:
    findings = [finding("a", 1.0), finding("b", None), finding("c", 9.6), finding("d", 0.0)]
    assert [f.resource_id for f in sort_by_savings(findings)] == ["c", "a", "d", "b"]


def test_total_ignores_unpriced() -> None:
    assert total_savings([finding("a", 9.6), finding("b", 1.92), finding("c", None)]) == 11.52


def test_report_has_summary_table_and_total() -> None:
    report = render_markdown([finding("vol-small", 1.92), finding("vol-big", 9.6)], [REGION], DAY)

    assert "Region: ap-southeast-1 · Scanned: 2026-01-15" in report
    assert "**You can save ~$11.52/month** (2 findings)" in report
    assert "| unattached-ebs | vol-big | ap-southeast-1 | test | $9.60 |" in report
    assert report.index("vol-big") < report.index("vol-small")
    assert "| **Total** | | | | **$11.52** |" in report


def test_report_marks_unpriced() -> None:
    report = render_markdown([finding("vol-a", None)], [REGION], DAY)

    assert "| n/a |" in report
    assert "1 finding(s) have no price" in report


def test_empty_report() -> None:
    report = render_markdown([], [REGION], DAY)

    assert "No waste found." in report
    assert "|" not in report


def test_pipes_are_escaped() -> None:
    report = render_markdown([finding("vol-a", 1.0, reason="a | b")], [REGION], DAY)
    assert "a \\| b" in report


def test_large_numbers_use_thousands_separator() -> None:
    report = render_markdown([finding("vol-a", 12345.6)], [REGION], DAY)
    assert "~$12,345.60/month" in report


def test_multi_region_header() -> None:
    report = render_markdown([], ["ap-southeast-1", "ap-southeast-2"], DAY)
    assert "Regions (2): ap-southeast-1, ap-southeast-2 · Scanned: 2026-01-15" in report


def test_markdown_verify_note() -> None:
    lb = Finding("idle-load-balancer", "app/x/1", "ap-southeast-1", "ALB idle", {}, 18.4)
    report = render_markdown([lb], ["ap-southeast-1"], date(2026, 1, 15))
    assert "ALB idle (verify before deleting)" in report
    assert "confirm with the resource owner" in report
