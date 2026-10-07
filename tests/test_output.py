import csv
import io
import json
import re
from datetime import date

import pytest
from click.testing import CliRunner

from cost_waste_finder.cli import cli
from cost_waste_finder.html_report import render_html
from cost_waste_finder.models import Finding
from cost_waste_finder.output import RENDERERS, render
from cost_waste_finder.report import csv_safe, render_csv, render_json

REGIONS = ["ap-southeast-1"]
DAY = date(2026, 1, 15)


def findings() -> list[Finding]:
    return [
        Finding("old-snapshot", "snap-0aaa1111bbbb2222c", "ap-southeast-1", "old", {}, 4.04),
        Finding("idle-nat-gateway", "nat-0ccc3333dddd4444e", "ap-southeast-1", "idle", {}, 43.07),
        Finding("unattached-eip", "eipalloc-0f1e2d3c", "ap-southeast-1", "unused", {}, None),
    ]


def test_csv_rows_sorted_with_header() -> None:
    rows = list(csv.reader(io.StringIO(render_csv(findings(), REGIONS, DAY))))

    assert rows[0] == ["check", "resource_id", "region", "reason", "monthly_cost_usd"]
    assert [r[1] for r in rows[1:]] == [
        "nat-0ccc3333dddd4444e",
        "snap-0aaa1111bbbb2222c",
        "eipalloc-0f1e2d3c",
    ]
    assert rows[1][4] == "43.07"
    assert rows[3][4] == ""  # no price


def test_csv_blocks_formula_injection() -> None:
    assert csv_safe("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert csv_safe("-1+1") == "'-1+1"
    assert csv_safe("vol-123") == "vol-123"


def test_json_report() -> None:
    report = json.loads(render_json(findings(), REGIONS, DAY))

    assert report["scanned_on"] == "2026-01-15"
    assert report["regions"] == REGIONS
    assert report["total_monthly_savings_usd"] == 47.11
    assert report["findings"][0]["resource_id"] == "nat-0ccc3333dddd4444e"
    assert report["findings"][2]["monthly_cost_usd"] is None


def test_html_report() -> None:
    page = render_html(findings(), REGIONS, DAY)

    assert page.startswith("<!doctype html>")
    assert "Potential savings per month" in page
    assert '<dd class="money">$47.11</dd>' in page
    assert page.index("nat-0ccc3333dddd4444e") < page.index("snap-0aaa1111bbbb2222c")
    assert "1 finding(s) have no price" in page
    assert "prefers-color-scheme: dark" in page


def test_html_escapes_text() -> None:
    bad = Finding("idle-load-balancer", "<b>x</b>", "ap-southeast-1", '<script>"x"</script>')
    page = render_html([bad], REGIONS, DAY)

    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "&lt;b&gt;x&lt;/b&gt;" in page


def test_html_has_no_external_resources() -> None:
    page = render_html(findings(), REGIONS, DAY)

    assert not re.search(r"https?://", page)
    assert "<script" not in page
    assert "<link" not in page


@pytest.mark.parametrize("fmt", list(RENDERERS))
def test_every_format_handles_no_findings(fmt: str) -> None:
    text = render([], REGIONS, fmt, DAY)
    assert text.strip()


def test_cli_writes_output_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr("cost_waste_finder.cli.scan_regions", lambda s, r, t: findings())
    target = tmp_path / "reports" / "client-a.html"

    result = CliRunner().invoke(
        cli, ["scan", "--region", "ap-southeast-1", "--format", "html", "--output", str(target)]
    )

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert f"Report written to {target}" in result.stderr
    assert '<dd class="money">$47.11</dd>' in target.read_text()


def test_cli_prints_chosen_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cost_waste_finder.cli.scan_regions", lambda s, r, t: findings())

    result = CliRunner().invoke(cli, ["scan", "--region", "ap-southeast-1", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["total_monthly_savings_usd"] == 47.11


def test_cli_rejects_unknown_format() -> None:
    result = CliRunner().invoke(cli, ["scan", "--region", "ap-southeast-1", "--format", "pdf"])
    assert result.exit_code != 0
    assert "pdf" in result.output
