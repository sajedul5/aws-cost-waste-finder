"""Self-contained HTML report: inline CSS, no scripts, nothing loaded from the web. Safe to email.

The only link is the optional "Prepared by" LinkedIn/email from the user's own branding.
`page()` can take a script, but only the local `cwf web` page passes one, never the report.

The look follows the AWS console and documentation (navy top bar, orange buttons, plain tables).
No AWS logo is used: this is not an official AWS document.
"""

from datetime import date, datetime
from html import escape

from cost_waste_finder.branding import Branding
from cost_waste_finder.models import Finding
from cost_waste_finder.report import (
    format_cost,
    plural,
    regions_label,
    report_reason,
    sort_by_savings,
    total_savings,
    verify_note,
)

PRODUCT = "AWS Cost Waste Audit"
DEFAULT_TITLE = "AWS Cost Waste Report"
FOOTER = "Read-only scan by cwf. On-demand list prices in USD; estimates, not a bill."

# AWS-console-like palette: squid-ink navy, orange actions, blue links, green for savings.
CSS = """
:root {
  --bg: #ffffff; --text: #000716; --muted: #5f6b7a; --border: #e9ebed; --head: #fafafa;
  --nav: #232f3e; --orange: #ff9900; --orange-hover: #ec7211; --link: #0972d3;
  --info-bg: #f2f8fd; --money: #037f0c; --code: #f4f4f4; --error: #d91515; --error-bg: #fff7f7;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1b2a; --text: #d1d5db; --muted: #8d99a8; --border: #414d5c; --head: #192534;
    --nav: #16191f; --link: #539fe5; --info-bg: #00142b; --money: #29ad32; --code: #192534;
    --error: #ff7a7a; --error-bg: #2a0f14;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.6 "Amazon Ember", "Helvetica Neue", Roboto, Arial, sans-serif;
}
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
.topbar { background: var(--nav); color: #fff; border-bottom: 3px solid var(--orange); }
.topbar-inner, main { max-width: 1120px; margin: 0 auto; padding: 0 20px; }
.topbar-inner { display: flex; align-items: center; gap: 12px; height: 48px; }
.product { font-weight: 700; font-size: 16px; }
.tag { font-size: 12px; color: #d5dbdb; border: 1px solid #5f6b7a; border-radius: 4px;
  padding: 0 6px; }
main { padding-top: 24px; padding-bottom: 40px; }
h1 { font-size: 28px; line-height: 1.25; font-weight: 700; margin: 0 0 4px; }
h2 { font-size: 20px; font-weight: 700; margin: 28px 0 12px; }
.subtitle, .meta { color: var(--muted); margin: 0 0 16px; }
.brand { display: flex; gap: 14px; align-items: center; background: var(--info-bg);
  border: 1px solid var(--link); border-left-width: 4px; border-radius: 8px;
  padding: 14px 18px; margin: 16px 0 8px; }
.brand-label { font-size: 12px; color: var(--muted); font-weight: 700; }
.brand-name { font-size: 18px; font-weight: 700; line-height: 1.3; }
.brand-title { color: var(--muted); }
.brand-links { margin-top: 4px; display: flex; gap: 16px; flex-wrap: wrap; font-weight: 700; }
.summary { border: 1px solid var(--border); border-radius: 8px; margin: 8px 0 0; }
.summary h2 { margin: 0; padding: 12px 18px; font-size: 18px;
  border-bottom: 1px solid var(--border); }
.summary dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  margin: 0; padding: 16px 18px; gap: 16px; }
.summary dt { color: var(--muted); font-size: 13px; }
.summary dd { margin: 2px 0 0; font-size: 24px; font-weight: 700; }
.summary dd.money { color: var(--money); }
.table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--border);
  vertical-align: top; }
th { background: var(--head); font-weight: 700; color: var(--muted); }
tbody tr:hover { background: var(--head); }
td.num, th.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
code, td.id { font-family: Monaco, Menlo, Consolas, "Courier New", monospace; font-size: 13px; }
td.nowrap, code { white-space: nowrap; }
code { background: var(--code); border-radius: 4px; padding: 1px 5px; }
tfoot td { font-weight: 700; border-bottom: none; }
tfoot td.num { color: var(--money); }
.note, footer { color: var(--muted); font-size: 13px; margin-top: 16px; }
footer { border-top: 1px solid var(--border); padding-top: 12px; margin-top: 32px; }
"""


def prepared_by_html(branding: Branding | None) -> str:
    """Highlighted "Prepared by" note, like an AWS docs info box. LinkedIn opens in a new tab."""
    if not branding:
        return ""
    links = []
    if branding.email:
        email = escape(branding.email)
        links.append(f'<a href="mailto:{email}">{email}</a>')
    if branding.linkedin_url:
        links.append(
            f'<a href="{escape(branding.linkedin_url)}" target="_blank" '
            'rel="noopener noreferrer">LinkedIn &#8599;</a>'
        )
    title = f'<div class="brand-title">{escape(branding.title)}</div>' if branding.title else ""
    link_row = f'<div class="brand-links">{"".join(links)}</div>' if links else ""
    return f"""
  <aside class="brand">
    <div>
      <div class="brand-label">Prepared by</div>
      <div class="brand-name">{escape(branding.name)}</div>{title}{link_row}
    </div>
  </aside>"""


def format_scanned(scanned: date | datetime | None) -> str:
    """ "2026-10-07 09:32 UTC" for a timestamp, "2026-10-07" for a plain date."""
    scanned = scanned or date.today()
    if isinstance(scanned, datetime):
        return scanned.strftime("%Y-%m-%d %H:%M UTC")
    return scanned.isoformat()


def page(
    title: str,
    body: str,
    subtitle: str = "",
    branding: Branding | None = None,
    extra_css: str = "",
    script: str = "",
) -> str:
    """A complete HTML document: navy top bar, title, "Prepared by" note, then `body`."""
    script_tag = f"\n<script>{script}</script>" if script else ""
    subtitle_html = f'\n  <p class="subtitle">{escape(subtitle)}</p>' if subtitle else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{CSS}{extra_css}</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <span class="product">{PRODUCT}</span><span class="tag">read-only</span>
  </div>
</header>
<main>
  <h1>{escape(title)}</h1>{subtitle_html}{prepared_by_html(branding)}{body}
  <footer>{FOOTER}</footer>
</main>{script_tag}
</body>
</html>
"""


def render_html(
    findings: list[Finding],
    regions: list[str],
    scanned_on: date | datetime | None = None,
    title: str = DEFAULT_TITLE,
    branding: Branding | None = None,
) -> str:
    subtitle = f"Scanned: {format_scanned(scanned_on)}"
    return page(title, report_body(findings, regions), subtitle, branding)


def report_body(findings: list[Finding], regions: list[str]) -> str:
    """The report itself: summary box, findings table and total."""
    regions_line = (
        f'\n    <p class="meta" style="padding:0 18px">{escape(regions_label(regions))}</p>'
    )
    if not findings:
        return f"""
  <section class="summary">
    <h2>Summary</h2>
    <dl><div><dt>Result</dt><dd class="money">No waste found</dd></div></dl>{regions_line}
  </section>"""
    total = total_savings(findings)
    return f"""
  <section class="summary">
    <h2>Summary</h2>
    <dl>
      <div><dt>Potential savings per month</dt><dd class="money">{format_cost(total)}</dd></div>
      <div><dt>Per year</dt><dd>{format_cost(total * 12)}</dd></div>
      <div><dt>Findings</dt><dd>{len(findings)}</dd></div>
    </dl>{regions_line}
  </section>
  <h2>Findings</h2>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Check</th><th>Resource ID</th><th>Region</th><th>Reason</th>
      <th class="num">Monthly cost</th></tr></thead>
    <tbody>
{_rows(findings)}
    </tbody>
    <tfoot><tr><td colspan="4">Total ({plural(len(findings), "finding")})</td>
      <td class="num">{format_cost(total)}</td></tr></tfoot>
  </table>
  </div>{_notes(findings)}"""


def _rows(findings: list[Finding]) -> str:
    rows = []
    for f in sort_by_savings(findings):
        rows.append(
            "      <tr>"
            f"<td><code>{escape(f.check)}</code></td>"
            f'<td class="id">{escape(f.resource_id)}</td>'
            f'<td class="nowrap">{escape(f.region)}</td>'
            f"<td>{escape(report_reason(f))}</td>"
            f'<td class="num">{format_cost(f.monthly_cost)}</td>'
            "</tr>"
        )
    return "\n".join(rows)


def _notes(findings: list[Finding]) -> str:
    notes = []
    unpriced = sum(1 for f in findings if f.monthly_cost is None)
    if unpriced:
        notes.append(f"{unpriced} finding(s) have no price (n/a) and are not in the total.")
    if note := verify_note(findings):
        notes.append(note)
    return "".join(f'\n  <p class="note">{escape(text)}</p>' for text in notes)
