"""Renders the 3-month bill trend as Markdown or JSON."""

import json
from datetime import timedelta

from cost_waste_finder.billing import percent_change
from cost_waste_finder.models import BillSummary, ServiceTrend
from cost_waste_finder.report import escape, format_cost

TOP_SERVICES = 10
TOP_MOVERS = 10


def format_change(before: float, after: float) -> str:
    """e.g. "▲ $184.45 (+15.3%)", "▼ $78.55 (-5.7%)", "new", or "-" when nothing changed."""
    diff = round(after - before, 2)
    if diff == 0:
        return "-"
    pct = percent_change(before, after)
    arrow = "▲" if diff > 0 else "▼"
    if pct is None:
        return f"{arrow} ${abs(diff):,.2f} (new)"
    return f"{arrow} ${abs(diff):,.2f} ({pct:+.1f}%)"


def movers(summary: BillSummary) -> tuple[list[ServiceTrend], list[ServiceTrend]]:
    """Biggest increases and decreases, last month vs the month before (by dollars)."""
    changed = [t for t in summary.services if t.change != 0 and t.service != "Other"]
    ups = sorted((t for t in changed if t.change > 0), key=lambda t: -t.change)
    downs = sorted((t for t in changed if t.change < 0), key=lambda t: t.change)
    return ups[:TOP_MOVERS], downs[:TOP_MOVERS]


def render_bill_markdown(summary: BillSummary) -> str:
    m2, m1, current = summary.months
    yesterday = summary.as_of - timedelta(days=1)
    to_day = f"{yesterday:%b} {yesterday.day}"
    lines = [
        "# AWS bill trend",
        "",
        f"As of {summary.as_of.isoformat()} · Cost Explorer, unblended cost, "
        "credits and refunds excluded · USD",
        "",
        "| Month | Total | Change vs previous month |",
        "|---|---:|---|",
        f"| {m2.label} | {format_cost(m2.total)} | |",
        f"| {m1.label} | {format_cost(m1.total)} | {format_change(m2.total, m1.total)} |",
        f"| {current.label} (so far, to {to_day}) | {format_cost(current.total)} | |",
    ]
    if current.projected is not None:
        lines.append(
            f"| {current.label} (projected, {current.projection_method}) "
            f"| {format_cost(current.projected)} | {format_change(m1.total, current.projected)} |"
        )

    lines += [
        "",
        "## Top services",
        "",
        f"| Service | {m2.label} | {m1.label} | {current.label} (proj.) | "
        f"Change {m1.label[:3]} vs {m2.label[:3]} |",
        "|---|---:|---:|---:|---|",
    ]
    for t in summary.services[:TOP_SERVICES]:
        lines.append(
            f"| {escape(t.service)} | {format_cost(t.month_2)} | {format_cost(t.month_1)} | "
            f"{format_cost(t.current_projected)} | {format_change(t.month_2, t.month_1)} |"
        )

    if current.projection_method == "AWS forecast":
        lines += [
            "",
            "Per-service projections scale the cost so far to the whole month, so they won't add "
            "up exactly to the AWS forecast above.",
        ]

    ups, downs = movers(summary)
    for title, group in (("Biggest increases", ups), ("Biggest decreases", downs)):
        lines += ["", f"## {title} ({m1.label[:3]} vs {m2.label[:3]})", ""]
        if not group:
            lines.append("None.")
            continue
        lines += ["| Service | Change |", "|---|---|"]
        lines += [f"| {escape(t.service)} | {format_change(t.month_2, t.month_1)} |" for t in group]
    return "\n".join(lines) + "\n"


def bill_to_dict(summary: BillSummary) -> dict:
    """Plain data for JSON (and the dashboard)."""
    ups, downs = movers(summary)
    return {
        "as_of": summary.as_of.isoformat(),
        "currency": "USD",
        "cost_explorer_calls": summary.api_calls,
        "months": [
            {
                "month": m.start.strftime("%Y-%m"),
                "label": m.label,
                "total": m.total,
                "partial": m.partial,
                "projected": m.projected,
                "projection_method": m.projection_method,
            }
            for m in summary.months
        ],
        "services": [
            {
                "service": t.service,
                "month_2": t.month_2,
                "month_1": t.month_1,
                "current_so_far": t.current_so_far,
                "current_projected": t.current_projected,
                "change": t.change,
                "change_pct": percent_change(t.month_2, t.month_1),
            }
            for t in summary.services
        ],
        "biggest_increases": [t.service for t in ups],
        "biggest_decreases": [t.service for t in downs],
    }


def render_bill_json(summary: BillSummary) -> str:
    return json.dumps(bill_to_dict(summary), indent=2) + "\n"


BILL_RENDERERS = {"markdown": render_bill_markdown, "json": render_bill_json}
