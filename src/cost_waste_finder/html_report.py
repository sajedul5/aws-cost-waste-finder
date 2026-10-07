"""Self-contained HTML report: inline CSS, no scripts, no external links. Safe to email."""

from datetime import date, datetime
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

DEFAULT_TITLE = "AWS Cost Waste Report"
FOOTER = "Read-only scan by cwf. On-demand list prices in USD; estimates, not a bill."

# Look of the HTML report and the web page. Indigo brand colour, green for money; light and dark.
CSS = """
:root {
  --bg: #f4f6fb; --surface: #ffffff; --text: #0f172a; --muted: #64748b;
  --border: #e2e8f0; --row: #f8fafc; --accent: #4f46e5; --accent-soft: #eef2ff;
  --money: #059669; --money-soft: #ecfdf5;
  --hero: linear-gradient(135deg, #312e81 0%, #4f46e5 55%, #7c3aed 100%);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0b1020; --surface: #131a2e; --text: #e5e7eb; --muted: #94a3b8;
    --border: #23304d; --row: #10172a; --accent: #a5b4fc; --accent-soft: #1e1b4b;
    --money: #34d399; --money-soft: #062e22;
    --hero: linear-gradient(135deg, #1e1b4b 0%, #3730a3 55%, #5b21b6 100%);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.6 "Inter", ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI",
    Roboto, "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.hero { background: var(--hero); color: #fff; padding: 36px 16px 40px; }
.hero-inner, main { max-width: 1080px; margin: 0 auto; }
.hero-inner { display: flex; gap: 24px; justify-content: space-between; align-items: center;
  flex-wrap: wrap; }
.eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 12px; font-weight: 600;
  opacity: 0.8; margin: 0 0 6px; }
h1 { font-size: clamp(26px, 4vw, 36px); line-height: 1.15; margin: 0; font-weight: 800;
  letter-spacing: -0.02em; }
.subtitle { margin: 10px 0 0; opacity: 0.85; font-size: 14px; }
.brand { display: flex; gap: 14px; align-items: center; background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 16px; padding: 16px 18px;
  backdrop-filter: blur(6px); min-width: 280px; }
.avatar { width: 52px; height: 52px; border-radius: 50%; background: #fff; color: #4338ca;
  display: grid; place-items: center; font-weight: 800; font-size: 18px; flex: none; }
.brand-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; opacity: 0.8; }
.brand-name { font-size: 18px; font-weight: 700; line-height: 1.3; }
.brand-title { font-size: 13px; opacity: 0.9; }
.brand-links { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px;
  border-radius: 999px; background: #fff; color: #312e81; font-size: 13px; font-weight: 600;
  text-decoration: none; }
.pill:hover { background: #e0e7ff; }
.pill.linkedin { background: #0a66c2; color: #fff; }
.pill.linkedin:hover { background: #004182; }
.in { font-weight: 800; font-family: Arial, sans-serif; }
main { padding: 28px 16px 40px; }
.meta { color: var(--muted); margin: 0 0 20px; font-size: 13px; }
.cards { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  margin-bottom: 24px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
  padding: 18px 20px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }
.card .label { color: var(--muted); font-size: 12px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.06em; }
.card .value { font-size: 30px; font-weight: 800; letter-spacing: -0.02em; margin-top: 4px; }
.card.money { background: var(--money-soft); border-color: transparent; }
.card.money .value { color: var(--money); }
.table-wrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 12px 16px; border-bottom: 1px solid var(--border); }
th { background: var(--accent-soft); color: var(--accent); font-weight: 700; font-size: 12px;
  text-transform: uppercase; letter-spacing: 0.05em; }
tbody tr:nth-child(even) { background: var(--row); }
td.num, th.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.num { font-weight: 600; }
td.id { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
.check { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px;
  font-weight: 600; background: var(--accent-soft); color: var(--accent); white-space: nowrap; }
tfoot td { font-weight: 800; border-bottom: none; font-size: 15px; }
tfoot td.num { color: var(--money); }
.note, footer { color: var(--muted); font-size: 13px; margin-top: 16px; }
"""


def initials(name: str) -> str:
    """ "Md Sajedul Islam" -> "SI": first letters of the last two words."""
    words = [w for w in name.split() if w[:1].isalpha()]
    return "".join(w[0].upper() for w in words[-2:]) or "?"


def prepared_by_html(branding: Branding | None) -> str:
    """Highlighted contact card for the coloured header. LinkedIn opens in a new tab."""
    if not branding:
        return ""
    links = []
    if branding.email:
        email = escape(branding.email)
        links.append(f'<a class="pill" href="mailto:{email}">&#9993; {email}</a>')
    if branding.linkedin_url:
        links.append(
            f'<a class="pill linkedin" href="{escape(branding.linkedin_url)}" '
            'target="_blank" rel="noopener noreferrer"><span class="in">in</span> LinkedIn</a>'
        )
    title = f'<div class="brand-title">{escape(branding.title)}</div>' if branding.title else ""
    link_row = f'<div class="brand-links">{"".join(links)}</div>' if links else ""
    return f"""
    <aside class="brand">
      <div class="avatar">{escape(initials(branding.name))}</div>
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
    eyebrow: str = "AWS cost audit",
) -> str:
    """A complete HTML document: coloured header (title + branding card), then `body`."""
    script_tag = f"\n<script>{script}</script>" if script else ""
    subtitle_html = f'<p class="subtitle">{escape(subtitle)}</p>' if subtitle else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{CSS}{extra_css}</style>
</head>
<body>
<header class="hero">
  <div class="hero-inner">
    <div>
      <p class="eyebrow">{escape(eyebrow)}</p>
      <h1>{escape(title)}</h1>{subtitle_html}
    </div>{prepared_by_html(branding)}
  </div>
</header>
<main>{body}
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
    """The report itself: regions, savings cards, findings table and total."""
    meta = f'\n  <p class="meta">{escape(regions_label(regions))}</p>'
    if not findings:
        return meta + (
            '\n  <section class="cards"><div class="card money"><div class="label">Result</div>'
            '<div class="value">No waste found</div></div></section>'
        )
    total = total_savings(findings)
    return f"""{meta}
  <section class="cards">
    <div class="card money"><div class="label">Potential savings</div>
      <div class="value">{format_cost(total)}/mo</div></div>
    <div class="card"><div class="label">Per year</div>
      <div class="value">{format_cost(total * 12)}</div></div>
    <div class="card"><div class="label">Findings</div>
      <div class="value">{len(findings)}</div></div>
  </section>
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
  </div>{_unpriced_note(findings)}"""


def _rows(findings: list[Finding]) -> str:
    rows = []
    for f in sort_by_savings(findings):
        rows.append(
            "      <tr>"
            f'<td><span class="check">{escape(f.check)}</span></td>'
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
