"""Bird's-eye HTML dashboard: bill trend + waste findings + actions, in one self-contained file.

No JavaScript and no external links: inline CSS (shared with the HTML report) and inline SVG.
"""

from collections import defaultdict
from datetime import date
from html import escape

from cost_waste_finder.billing_report import format_change, movers
from cost_waste_finder.html_report import CSS
from cost_waste_finder.models import BillSummary, Finding
from cost_waste_finder.report import (
    format_cost,
    plural,
    regions_label,
    sort_by_savings,
    total_savings,
)

TOP_SERVICES = 10
TOP_MOVERS = 5
TOP_FINDINGS = 10
TOP_ACTIONS = 3

# What to do about each kind of finding, in plain words for a client.
ACTIONS = {
    "unattached-ebs": "Snapshot the volume if the data may be needed, then delete it.",
    "old-snapshot": "Confirm no one needs it, then delete it or move it to the archive tier.",
    "unattached-eip": "Release the Elastic IP (EC2 → Elastic IPs) if nothing will use it.",
    "gp2-to-gp3": "Change the volume type to gp3 in the EC2 console. No downtime.",
    "idle-ec2": "Check with the owner; stop it, schedule it, or move to a smaller type.",
    "idle-nat-gateway": "Delete it if the private subnets don't need internet access.",
    "idle-load-balancer": "Delete it if no app uses it (check DNS records first).",
    "stopped-ec2": "Create an AMI as a backup, then terminate the instance and its volumes.",
}

DASHBOARD_CSS = """
main { max-width: 1120px; }
h2 { font-size: 16px; margin: 32px 0 12px; }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px 18px;
}
.card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; }
.card .value { font-size: 26px; font-weight: 650; margin: 2px 0; }
.card .sub { font-size: 13px; color: var(--muted); }
.card.savings .value { color: var(--accent); }
.up { color: var(--up); }
.down { color: var(--down); }
.two { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.chart svg { width: 100%; height: auto; display: block; }
.chart .bar { fill: var(--accent); }
.chart .hatch-fill { fill: var(--accent); opacity: 0.45; }
.chart text { fill: var(--muted); font-size: 12px; }
.chart text.bar-amount { fill: var(--text); font-weight: 600; }
.hbar { display: grid; grid-template-columns: 150px 1fr 80px; gap: 10px; align-items: center;
  font-size: 13px; margin: 8px 0; }
.hbar .track { background: var(--row); border-radius: 4px; height: 10px; }
.hbar .fill { background: var(--accent); border-radius: 4px; height: 10px; }
.hbar .amount { text-align: right; font-variant-numeric: tabular-nums; }
ol.actions { margin: 0; padding-left: 20px; }
ol.actions li { margin: 8px 0; }
.empty { color: var(--muted); }
:root { --up: #b42318; --down: #067647; }
@media (prefers-color-scheme: dark) { :root { --up: #f97066; --down: #47cd89; } }
"""


def render_dashboard(
    findings: list[Finding],
    regions: list[str],
    bill: BillSummary | None,
    title: str | None = None,
    scanned_on: date | None = None,
) -> str:
    scanned_on = scanned_on or date.today()
    heading = f"{title} · AWS cost dashboard" if title else "AWS cost dashboard"
    sections = [
        _kpis(findings, bill),
        _bill_sections(bill),
        _waste_sections(findings),
        _actions(findings),
    ]
    sources = "EC2/ELB/CloudWatch Describe calls, AWS Pricing API" + (
        ", Cost Explorer" if bill else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(heading)}</title>
<style>{CSS}{DASHBOARD_CSS}</style>
</head>
<body>
<main>
  <h1>{escape(heading)}</h1>
  <p class="meta">{escape(regions_label(regions))} · Generated {scanned_on.isoformat()}</p>
{"".join(sections)}
  <footer>Data: {sources}. Read-only. Savings use on-demand list prices in USD (no Savings Plans
  or RI discounts); the forecast is AWS's estimate. Snapshot savings are an upper bound.</footer>
</main>
</body>
</html>
"""


# --- headline numbers -------------------------------------------------------------------------


def _kpis(findings: list[Finding], bill: BillSummary | None) -> str:
    savings = total_savings(findings)
    cards = []
    if bill:
        m2, m1, current = bill.months
        this_month = current.projected if current.projected is not None else current.total
        cards.append(
            _card(
                f"{current.label} (projected)",
                format_cost(this_month),
                _change_html(m1.total, this_month, "vs last month"),
            )
        )
        cards.append(
            _card(
                f"{m1.label} bill",
                format_cost(m1.total),
                _change_html(m2.total, m1.total, f"vs {m2.label[:3]}"),
            )
        )
    cards.append(
        _card(
            "Potential savings",
            f"{format_cost(savings)}/mo",
            escape(plural(len(findings), "finding")),
            "savings",
        )
    )
    if bill:
        share = savings_share(findings, bill)
        value = "n/a" if share is None else f"{share:.1f}%"
        cards.append(_card("Savings vs bill", value, "of last month's bill"))
    else:
        cards.append(_card("Bill trend", "Not included", "run without --no-bill to add it"))
    return f'  <section class="grid">{"".join(cards)}</section>\n'


def _card(label: str, value: str, sub: str, extra_class: str = "") -> str:
    return (
        f'<div class="card {extra_class}"><div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(value)}</div><div class="sub">{sub}</div></div>'
    )


def _change_html(before: float, after: float, suffix: str) -> str:
    """Cost going up is bad (red), down is good (green)."""
    text = format_change(before, after)
    css = "up" if after > before else "down" if after < before else ""
    return f'<span class="{css}">{escape(text)}</span> {escape(suffix)}'


# --- bill ------------------------------------------------------------------------------------


def _bill_sections(bill: BillSummary | None) -> str:
    if not bill:
        return ""
    m2, m1, current = bill.months
    rows = "".join(
        f"<tr><td>{escape(t.service)}</td><td class='num'>{format_cost(t.month_2)}</td>"
        f"<td class='num'>{format_cost(t.month_1)}</td>"
        f"<td class='num'>{format_cost(t.current_projected)}</td>"
        f"<td>{_change_html(t.month_2, t.month_1, '')}</td></tr>"
        for t in bill.services[:TOP_SERVICES]
    )
    ups, downs = movers(bill)
    return f"""
  <h2>Bill: last 3 months</h2>
  <div class="two">
    <div class="card chart">{bill_chart_svg(bill)}</div>
    <div class="card">
      <div class="label">Biggest increases ({m1.label[:3]} vs {m2.label[:3]})</div>
      {_movers_list(ups[:TOP_MOVERS])}
      <div class="label" style="margin-top:14px">Biggest decreases</div>
      {_movers_list(downs[:TOP_MOVERS])}
    </div>
  </div>
  <h2>Top services</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Service</th><th class="num">{m2.label}</th><th class="num">{m1.label}</th>
      <th class="num">{current.label} (proj.)</th><th>Change</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
"""


def _movers_list(trends) -> str:
    if not trends:
        return '<p class="empty">None.</p>'
    items = "".join(
        f"<li>{escape(t.service)}: {_change_html(t.month_2, t.month_1, '')}</li>" for t in trends
    )
    return f'<ul style="margin:6px 0 0;padding-left:18px">{items}</ul>'


def bar_heights(values: list[float], max_height: float) -> list[float]:
    """Scale values to bar heights; all-zero values give zero-height bars."""
    top = max(values, default=0)
    if top <= 0:
        return [0.0 for _ in values]
    return [round(v / top * max_height, 1) for v in values]


def bill_chart_svg(bill: BillSummary) -> str:
    """Bars for the 2 full months and the current month (so far solid, rest projected hatched)."""
    m2, m1, current = bill.months
    projected = current.projected if current.projected is not None else current.total
    width, height, base, bar_width, chart_height = 420, 230, 190, 80, 150
    heights = bar_heights([m2.total, m1.total, projected, current.total], chart_height)
    full, so_far = heights[:3], heights[3]
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Bill: {escape(m2.label)} {format_cost(m2.total)}, '
        f"{escape(m1.label)} {format_cost(m1.total)}, "
        f'{escape(current.label)} projected {format_cost(projected)}">',
        '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><rect width="3" height="6" class="hatch-fill"/>'
        "</pattern></defs>",
    ]
    labels = [(m2.label, m2.total), (m1.label, m1.total), (f"{current.label} (proj.)", projected)]
    for index, ((label, amount), bar) in enumerate(zip(labels, full, strict=True)):
        x = 40 + index * 130
        if index < 2:
            parts.append(_rect(x, base - bar, bar_width, bar, "bar"))
        else:
            # projected part hatched on top of the solid "so far" part
            parts.append(_rect(x, base - bar, bar_width, bar - so_far, None, 'fill="url(#hatch)"'))
            parts.append(_rect(x, base - so_far, bar_width, so_far, "bar"))
        parts.append(
            f'<text class="bar-amount" x="{x + bar_width / 2}" y="{base - bar - 8}" '
            f'text-anchor="middle">{format_cost(amount)}</text>'
        )
        parts.append(
            f'<text x="{x + bar_width / 2}" y="{base + 20}" text-anchor="middle">'
            f"{escape(label)}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


def _rect(x: float, y: float, w: float, h: float, css: str | None, extra: str = "") -> str:
    css_attr = f' class="{css}"' if css else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{max(h, 0)}" rx="3"{css_attr} {extra}/>'


# --- waste -----------------------------------------------------------------------------------


def _waste_sections(findings: list[Finding]) -> str:
    if not findings:
        return '\n  <h2>Waste</h2>\n  <p class="empty">No waste found.</p>\n'
    rows = "".join(
        f"<tr><td>{escape(f.check)}</td><td class='id'>{escape(f.resource_id)}</td>"
        f"<td>{escape(f.region)}</td><td>{escape(f.reason)}</td>"
        f"<td class='num'>{format_cost(f.monthly_cost)}</td></tr>"
        for f in sort_by_savings(findings)[:TOP_FINDINGS]
    )
    more = len(findings) - TOP_FINDINGS
    note = (
        f'<p class="note">{more} more finding(s): run <code>cwf scan</code> for the full list.</p>'
        if more > 0
        else ""
    )
    return f"""
  <h2>Waste: potential savings</h2>
  <div class="two">
    <div class="card"><div class="label">By check</div>{_hbars(_group(findings, "check"))}</div>
    <div class="card"><div class="label">By region</div>{_hbars(_group(findings, "region"))}</div>
  </div>
  <h2>Top findings</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Check</th><th>Resource ID</th><th>Region</th><th>Reason</th>
      <th class="num">Monthly cost</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>{note}
"""


def _group(findings: list[Finding], attribute: str) -> list[tuple[str, float]]:
    totals: dict[str, float] = defaultdict(float)
    for f in findings:
        totals[getattr(f, attribute)] += f.monthly_cost or 0
    return sorted(((k, round(v, 2)) for k, v in totals.items()), key=lambda kv: -kv[1])


def _hbars(items: list[tuple[str, float]]) -> str:
    top = max((amount for _, amount in items), default=0)
    bars = []
    for name, amount in items:
        pct = amount / top * 100 if top else 0
        bars.append(
            f'<div class="hbar"><span>{escape(name)}</span>'
            f'<div class="track"><div class="fill" style="width:{pct:.1f}%"></div></div>'
            f'<span class="amount">{format_cost(amount)}</span></div>'
        )
    return "".join(bars)


# --- actions ---------------------------------------------------------------------------------


def _actions(findings: list[Finding]) -> str:
    top = [f for f in sort_by_savings(findings) if f.monthly_cost][:TOP_ACTIONS]
    if not top:
        return ""
    items = "".join(
        f"<li><strong>{format_cost(f.monthly_cost)}/mo</strong> · "
        f"<span class='id'>{escape(f.resource_id)}</span> ({escape(f.region)}): "
        f"{escape(ACTIONS.get(f.check, 'Review this resource.'))}</li>"
        for f in top
    )
    return f"""
  <h2>Recommended actions</h2>
  <div class="card"><ol class="actions">{items}</ol></div>
"""


def savings_share(findings: list[Finding], bill: BillSummary | None) -> float | None:
    """Potential savings as a % of last month's bill (None without a bill or with a $0 bill)."""
    if not bill or not bill.months[1].total:
        return None
    return round(total_savings(findings) / bill.months[1].total * 100, 1)
