"""Renders findings as Markdown, CSV, JSON or HTML, sorted by monthly savings."""

import csv
import io
import json
from datetime import date

from cost_waste_finder.models import Finding

CSV_COLUMNS = ["check", "resource_id", "region", "reason", "monthly_cost_usd"]


def sort_by_savings(findings: list[Finding]) -> list[Finding]:
    """Highest monthly cost first; findings without a price go last."""
    return sorted(findings, key=lambda f: (f.monthly_cost is None, -(f.monthly_cost or 0)))


def total_savings(findings: list[Finding]) -> float:
    return round(sum(f.monthly_cost or 0 for f in findings), 2)


def render_markdown(
    findings: list[Finding], regions: list[str], scanned_on: date | None = None
) -> str:
    scanned_on = scanned_on or date.today()
    lines = [
        "# AWS cost waste report",
        "",
        f"{regions_label(regions)} · Scanned: {scanned_on.isoformat()}",
        "",
    ]
    if not findings:
        lines.append("No waste found.")
        return "\n".join(lines) + "\n"

    total = total_savings(findings)
    lines += [
        f"**You can save ~${total:,.2f}/month** ({plural(len(findings), 'finding')})",
        "",
        "| Check | Resource ID | Region | Reason | Monthly cost |",
        "|---|---|---|---|---:|",
    ]
    for f in sort_by_savings(findings):
        cells = [f.check, f.resource_id, f.region, f.reason, format_cost(f.monthly_cost)]
        lines.append("| " + " | ".join(escape(cell) for cell in cells) + " |")
    lines.append(f"| **Total** | | | | **${total:,.2f}** |")

    unpriced = sum(1 for f in findings if f.monthly_cost is None)
    if unpriced:
        lines += ["", f"{unpriced} finding(s) have no price (n/a) and are not in the total."]
    return "\n".join(lines) + "\n"


def regions_label(regions: list[str]) -> str:
    if len(regions) == 1:
        return f"Region: {regions[0]}"
    return f"Regions ({len(regions)}): {', '.join(regions)}"


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def format_cost(cost: float | None) -> str:
    return "n/a" if cost is None else f"${cost:,.2f}"


def escape(text: str) -> str:
    """Keep table cells from breaking the Markdown table."""
    return text.replace("|", "\\|").replace("\n", " ")


def render_csv(findings: list[Finding], regions: list[str], scanned_on: date | None = None) -> str:
    """One row per finding, highest saving first. Data only: no total row."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for f in sort_by_savings(findings):
        cost = "" if f.monthly_cost is None else f"{f.monthly_cost:.2f}"
        writer.writerow(
            [csv_safe(f.check), csv_safe(f.resource_id), f.region, csv_safe(f.reason), cost]
        )
    return out.getvalue()


def render_json(findings: list[Finding], regions: list[str], scanned_on: date | None = None) -> str:
    report = {
        "scanned_on": (scanned_on or date.today()).isoformat(),
        "regions": regions,
        "total_monthly_savings_usd": total_savings(findings),
        "findings": [
            {
                "check": f.check,
                "resource_id": f.resource_id,
                "region": f.region,
                "reason": f.reason,
                "monthly_cost_usd": f.monthly_cost,
                "details": f.details,
            }
            for f in sort_by_savings(findings)
        ],
    }
    return json.dumps(report, indent=2) + "\n"


def csv_safe(text: str) -> str:
    """Stop spreadsheet apps from running a cell as a formula (CSV injection)."""
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text
