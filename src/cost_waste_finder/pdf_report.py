"""PDF version of the waste report, to share with a client. Built with fpdf2 (pure Python)."""

from datetime import date

from fpdf import FPDF
from fpdf.fonts import FontFace

from cost_waste_finder.branding import Branding
from cost_waste_finder.models import Finding
from cost_waste_finder.report import (
    format_cost,
    plural,
    regions_label,
    sort_by_savings,
    total_savings,
)

ACCENT = (15, 118, 110)  # same teal as the HTML report
MUTED = (107, 107, 102)
HEADER_FILL = (240, 240, 236)
COLUMN_WIDTHS = (34, 52, 30, 120, 31)  # mm on landscape A4 (277 mm usable)
BRAND_WIDTH = 75  # mm, "Prepared by" block in the top right corner


def safe(text: str) -> str:
    """The built-in PDF fonts only cover Latin-1; replace anything else instead of failing."""
    return text.encode("latin-1", "replace").decode("latin-1")


class ReportPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(*MUTED)
        self.cell(
            0,
            6,
            "Read-only scan by cwf. On-demand list prices in USD; estimates, not a bill.",
            align="L",
        )
        self.cell(0, 6, f"Page {self.page_no()}", align="R")


def render_pdf(
    findings: list[Finding],
    regions: list[str],
    organization: str = "",
    scanned_on: date | None = None,
    compress: bool = True,
    branding: Branding | None = None,
) -> bytes:
    scanned_on = scanned_on or date.today()
    pdf = ReportPDF(orientation="L", unit="mm", format="A4")
    pdf.compress = compress
    title = report_title(organization)
    pdf.set_title(safe(title))
    if branding:
        pdf.set_author(safe(branding.name))
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    brand_bottom = _prepared_by(pdf, branding) if branding else pdf.t_margin
    text_width = pdf.epw - (BRAND_WIDTH + 8 if branding else 0)
    pdf.set_xy(pdf.l_margin, pdf.t_margin)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(text_width, 9, safe(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*MUTED)
    meta = f"{regions_label(regions)} | Scanned: {scanned_on.isoformat()}"
    pdf.multi_cell(text_width, 5, safe(meta), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(pdf.get_y(), brand_bottom))
    pdf.ln(4)

    if not findings:
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "No waste found.")
        return bytes(pdf.output())

    total = total_savings(findings)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, "You can save about", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*ACCENT)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 11, f"{format_cost(total)}/month", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*MUTED)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(
        0,
        6,
        f"{plural(len(findings), 'finding')} ({format_cost(total * 12)}/year)",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", size=8.5)
    heading = FontFace(emphasis="BOLD", fill_color=HEADER_FILL)
    with pdf.table(
        col_widths=COLUMN_WIDTHS,
        text_align=("LEFT", "LEFT", "LEFT", "LEFT", "RIGHT"),
        headings_style=heading,
        line_height=5,
    ) as table:
        table.row(["Check", "Resource ID", "Region", "Reason", "Monthly cost"])
        for f in sort_by_savings(findings):
            table.row(
                [
                    safe(f.check),
                    safe(f.resource_id),
                    safe(f.region),
                    safe(f.reason),
                    format_cost(f.monthly_cost),
                ]
            )
        total_row = table.row(style=FontFace(emphasis="BOLD"))
        total_row.cell("Total", colspan=4)
        total_row.cell(format_cost(total))

    unpriced = sum(1 for f in findings if f.monthly_cost is None)
    if unpriced:
        pdf.ln(3)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 5, f"{unpriced} finding(s) have no price (n/a) and are not in the total.")
    return bytes(pdf.output())


def report_title(organization: str) -> str:
    return f"{organization} - AWS Cost Waste Report" if organization else "AWS Cost Waste Report"


def _prepared_by(pdf: FPDF, branding: Branding) -> float:
    """Top-right contact block with clickable email and LinkedIn. Returns its bottom y."""
    x = pdf.w - pdf.r_margin - BRAND_WIDTH
    pdf.set_xy(x, pdf.t_margin)
    lines: list[tuple[str, str, str]] = [  # (text, style, link)
        ("Prepared by", "", ""),
        (branding.name, "B", ""),
    ]
    if branding.title:
        lines.append((branding.title, "", ""))
    if branding.email:
        lines.append((branding.email, "U", f"mailto:{branding.email}"))
    if branding.linkedin_url:
        lines.append((f"LinkedIn: {branding.linkedin_label}", "U", branding.linkedin_url))

    for text, style, link in lines:
        pdf.set_x(x)
        pdf.set_font("Helvetica", style, 10 if style == "B" else 8.5)
        if link:
            pdf.set_text_color(*ACCENT)
        elif text == "Prepared by":
            pdf.set_text_color(*MUTED)
        else:
            pdf.set_text_color(0, 0, 0)
        pdf.cell(BRAND_WIDTH, 5, safe(text), align="R", link=link, new_x="LMARGIN", new_y="NEXT")
    return pdf.get_y()
