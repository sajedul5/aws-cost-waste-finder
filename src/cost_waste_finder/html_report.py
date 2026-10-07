"""Self-contained HTML report: inline CSS, no scripts, no external links. Safe to email."""

from datetime import date
from html import escape

from cost_waste_finder.branding import Branding
from cost_waste_finder.models import Finding
from cost_waste_finder.report import (
    format_cost,
    plural,
    regions_label,
    sort_by_savings,
    total_savings,
)

# Look of the HTML report (also used by the web page). Light and dark mode.
CSS = """
:root {
  --bg: #f7f7f5; --surface: #ffffff; --text: #1d1d1b; --muted: #6b6b66;
  --border: #e3e3de; --accent: #0f766e; --row: #fbfbf9;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161615; --surface: #1f1f1d; --text: #ececea; --muted: #a3a39e;
    --border: #33332f; --accent: #5eead4; --row: #232321;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 32px 16px; background: var(--bg); color: var(--text);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 1040px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; }
.meta { color: var(--muted); margin: 0 0 24px; font-size: 13px; }
.kpi {
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 20px 24px; margin-bottom: 24px;
}
.kpi .label { color: var(--muted); font-size: 13px; }
.kpi .value { font-size: 34px; font-weight: 650; color: var(--accent); }
.table-wrap {
  overflow-x: auto; background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px;
}
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-weight: 600; font-size: 12px; text-transform: uppercase; }
tbody tr:nth-child(even) { background: var(--row); }
td.num, th.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.id { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
tfoot td { font-weight: 650; border-bottom: none; }
.note, footer { color: var(--muted); font-size: 13px; margin-top: 16px; }
.prepared-by { float: right; text-align: right; font-size: 13px; line-height: 1.6;
  margin: 0 0 16px 24px; }
.prepared-by .label { color: var(--muted); font-size: 12px; }
.prepared-by a { color: var(--accent); }
@media (max-width: 640px) { .prepared-by { float: none; text-align: left; margin: 0 0 16px; } }
"""


def render_html(
    findings: list[Finding],
    regions: list[str],
    scanned_on: date | None = None,
    title: str = "AWS cost waste report",
    branding: Branding | None = None,
) -> str:
    return page(title, prepared_by_html(branding) + report_body(findings, regions, scanned_on))


def prepared_by_html(branding: Branding | None) -> str:
    """Contact block; links open in a new tab."""
    if not branding:
        return ""
    new_tab = 'target="_blank" rel="noopener noreferrer"'
    parts = ['<span class="label">Prepared by</span>', f"<strong>{escape(branding.name)}</strong>"]
    if branding.title:
        parts.append(escape(branding.title))
    if branding.email:
        email = escape(branding.email)
        parts.append(f'<a href="mailto:{email}">{email}</a>')
    if branding.linkedin_url:
        parts.append(
            f'<a href="{escape(branding.linkedin_url)}" {new_tab}>'
            f"LinkedIn: {escape(branding.linkedin_label)}</a>"
        )
    return '\n  <aside class="prepared-by">' + "<br>".join(parts) + "</aside>"


def page(title: str, body: str, extra_css: str = "", script: str = "") -> str:
    """A complete HTML document around `body` (already escaped HTML)."""
    script_tag = f"\n<script>{script}</script>" if script else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{CSS}{extra_css}</style>
</head>
<body>
<main>
  <h1>{escape(title)}</h1>{body}
  <footer>Read-only scan by cwf. On-demand list prices in USD; estimates, not a bill.</footer>
</main>{script_tag}
</body>
</html>
"""


def report_body(findings: list[Finding], regions: list[str], scanned_on: date | None = None) -> str:
    """The report itself: meta line, savings headline, findings table and total."""
    scanned_on = scanned_on or date.today()
    total = total_savings(findings)
    meta = f"{regions_label(regions)} · Scanned: {scanned_on.isoformat()}"
    if not findings:
        summary = '\n  <section class="kpi"><div class="value">No waste found.</div></section>'
    else:
        summary = f"""
  <section class="kpi">
    <div class="label">You can save about</div>
    <div class="value">{format_cost(total)}/month</div>
    <div class="label">{plural(len(findings), "finding")}</div>
  </section>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Check</th><th>Resource ID</th><th>Region</th><th>Reason</th>
      <th class="num">Monthly cost</th></tr></thead>
    <tbody>
{_rows(findings)}
    </tbody>
    <tfoot><tr><td colspan="4">Total</td><td class="num">{format_cost(total)}</td></tr></tfoot>
  </table>
  </div>{_unpriced_note(findings)}"""
    return f'\n  <p class="meta">{escape(meta)}</p>{summary}'


def _rows(findings: list[Finding]) -> str:
    rows = []
    for f in sort_by_savings(findings):
        rows.append(
            "      <tr>"
            f"<td>{escape(f.check)}</td>"
            f'<td class="id">{escape(f.resource_id)}</td>'
            f"<td>{escape(f.region)}</td>"
            f"<td>{escape(f.reason)}</td>"
            f'<td class="num">{format_cost(f.monthly_cost)}</td>'
            "</tr>"
        )
    return "\n".join(rows)


def _unpriced_note(findings: list[Finding]) -> str:
    unpriced = sum(1 for f in findings if f.monthly_cost is None)
    if not unpriced:
        return ""
    text = f"{unpriced} finding(s) have no price (n/a) and are not in the total."
    return f'\n  <p class="note">{text}</p>'
