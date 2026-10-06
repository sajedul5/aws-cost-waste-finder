"""Renders findings as a Markdown report sorted by monthly savings."""

from datetime import date

from cost_waste_finder.models import Finding


def sort_by_savings(findings: list[Finding]) -> list[Finding]:
    """Highest monthly cost first; findings without a price go last."""
    return sorted(findings, key=lambda f: (f.monthly_cost is None, -(f.monthly_cost or 0)))


def total_savings(findings: list[Finding]) -> float:
    return round(sum(f.monthly_cost or 0 for f in findings), 2)


def render_markdown(findings: list[Finding], region: str, scanned_on: date | None = None) -> str:
    scanned_on = scanned_on or date.today()
    lines = [
        "# AWS cost waste report",
        "",
        f"Region: {region} · Scanned: {scanned_on.isoformat()}",
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


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def format_cost(cost: float | None) -> str:
    return "n/a" if cost is None else f"${cost:,.2f}"


def escape(text: str) -> str:
    """Keep table cells from breaking the Markdown table."""
    return text.replace("|", "\\|").replace("\n", " ")
