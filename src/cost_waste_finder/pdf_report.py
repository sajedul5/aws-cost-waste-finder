"""PDF version of the waste report, to share with a client. Built with fpdf2 (pure Python)."""

from datetime import date, datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

from cost_waste_finder.branding import Branding
from cost_waste_finder.html_report import format_scanned
from cost_waste_finder.models import Finding
from cost_waste_finder.report import (
    format_cost,
    plural,
    regions_label,
    sort_by_savings,
    total_savings,
)

# Same colours as the HTML report: indigo brand, green for money.
INDIGO = (79, 70, 229)
INDIGO_DARK = (49, 46, 129)
INDIGO_SOFT = (238, 242, 255)
INDIGO_TEXT = (55, 48, 163)
MONEY = (5, 150, 105)
MONEY_SOFT = (236, 253, 245)
MUTED = (100, 116, 139)
TEXT = (15, 23, 42)
WHITE = (255, 255, 255)
LINKEDIN = (10, 102, 194)

BAND_HEIGHT = 38  # mm, coloured header on page 1
BRAND_WIDTH = 82  # mm, "Prepared by" block inside the header
COLUMN_WIDTHS = (36, 52, 30, 120, 29)  # mm on landscape A4 (277 mm usable)


def safe(text: str) -> str:
    """The built-in PDF fonts only cover Latin-1; replace anything else instead of failing."""
    return text.encode("latin-1", "replace").decode("latin-1")


def report_title(organization: str) -> str:
    return f"{organization} - AWS Cost Waste Report" if organization else "AWS Cost Waste Report"


class ReportPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(*MUTED)
        note = "Read-only scan by cwf. On-demand list prices in USD; estimates, not a bill."
        self.cell(0, 6, note, align="L")
        self.cell(0, 6, f"Page {self.page_no()}", align="R")


def render_pdf(
    findings: list[Finding],
    regions: list[str],
    organization: str = "",
    scanned_on: date | datetime | None = None,
    compress: bool = True,
    branding: Branding | None = None,
) -> bytes:
    pdf = ReportPDF(orientation="L", unit="mm", format="A4")
    pdf.compress = compress
    title = report_title(organization)
    pdf.set_title(safe(title))
    if branding:
        pdf.set_author(safe(branding.name))
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    _header_band(pdf, title, f"Scanned: {format_scanned(scanned_on)}", branding)
    pdf.set_font("Helvetica", size=8.5)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 4.5, safe(regions_label(regions)), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    if not findings:
        _stat(pdf, pdf.l_margin, "RESULT", "No waste found", MONEY_SOFT, MONEY, 90)
        return bytes(pdf.output())

    total = total_savings(findings)
    y = pdf.get_y()
    _stat(pdf, pdf.l_margin, "POTENTIAL SAVINGS", f"{format_cost(total)}/mo", MONEY_SOFT, MONEY)
    _stat(pdf, pdf.l_margin + 72, "PER YEAR", format_cost(total * 12), INDIGO_SOFT, TEXT)
    _stat(pdf, pdf.l_margin + 144, "FINDINGS", str(len(findings)), INDIGO_SOFT, TEXT)
    pdf.set_xy(pdf.l_margin, y + 26)

    pdf.set_text_color(*TEXT)
    pdf.set_draw_color(226, 232, 240)
    pdf.set_font("Helvetica", size=8.5)
    heading = FontFace(emphasis="BOLD", color=INDIGO_TEXT, fill_color=INDIGO_SOFT)
    with pdf.table(
        col_widths=COLUMN_WIDTHS,
        text_align=("LEFT", "LEFT", "LEFT", "LEFT", "RIGHT"),
        headings_style=heading,
        line_height=5.5,
        borders_layout="HORIZONTAL_LINES",
        padding=1.5,
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
        total_row = table.row(style=FontFace(emphasis="BOLD", color=MONEY))
        total_row.cell(f"Total ({plural(len(findings), 'finding')})", colspan=4)
        total_row.cell(format_cost(total))

    unpriced = sum(1 for f in findings if f.monthly_cost is None)
    if unpriced:
        pdf.ln(3)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 5, f"{unpriced} finding(s) have no price (n/a) and are not in the total.")
    return bytes(pdf.output())


def _header_band(pdf: FPDF, title: str, subtitle: str, branding: Branding | None) -> None:
    """Indigo band across the top: title on the left, highlighted "Prepared by" on the right."""
    pdf.set_fill_color(*INDIGO_DARK)
    pdf.rect(0, 0, pdf.w, BAND_HEIGHT, style="F")
    pdf.set_fill_color(*INDIGO)
    pdf.rect(0, BAND_HEIGHT - 2, pdf.w, 2, style="F")  # accent line

    text_width = pdf.epw - (BRAND_WIDTH + 10 if branding else 0)
    pdf.set_xy(pdf.l_margin, 9)
    pdf.set_text_color(199, 210, 254)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(text_width, 4, "AWS COST AUDIT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 19)
    pdf.multi_cell(text_width, 9, safe(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(224, 231, 255)
    pdf.cell(text_width, 5, safe(subtitle), new_x="LMARGIN", new_y="NEXT")

    if branding:
        _prepared_by(pdf, branding)
    pdf.set_xy(pdf.l_margin, BAND_HEIGHT + 5)


def _prepared_by(pdf: FPDF, branding: Branding) -> None:
    x = pdf.w - pdf.r_margin - BRAND_WIDTH
    pdf.set_fill_color(67, 56, 202)
    pdf.rect(x - 4, 5, BRAND_WIDTH + 4, BAND_HEIGHT - 10, style="F", round_corners=True)
    pdf.set_xy(x, 8)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(199, 210, 254)
    pdf.cell(BRAND_WIDTH - 2, 4, "PREPARED BY", align="R", new_x="LEFT", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*WHITE)
    pdf.cell(BRAND_WIDTH - 2, 6, safe(branding.name), align="R", new_x="LEFT", new_y="NEXT")
    if branding.title:
        pdf.set_font("Helvetica", size=8.5)
        pdf.set_text_color(224, 231, 255)
        title = safe(branding.title.replace("|", "\u00b7"))  # "|" looks like "I" in Helvetica
        pdf.cell(BRAND_WIDTH - 2, 4.5, title, align="R", new_x="LEFT", new_y="NEXT")
    links = []
    if branding.email:
        links.append((branding.email, f"mailto:{branding.email}"))
    if branding.linkedin_url:
        links.append(("LinkedIn", branding.linkedin_url))
    if links:
        _link_row(pdf, x + BRAND_WIDTH - 2, pdf.get_y() + 1.5, links)


def _link_row(pdf: FPDF, right: float, y: float, links: list[tuple[str, str]]) -> None:
    """Small "pills" (email, LinkedIn) right-aligned at `right`, each a clickable link."""
    pdf.set_font("Helvetica", "B", 8)
    gap, pad, height = 2, 2.5, 5.5
    widths = [pdf.get_string_width(safe(text)) + 2 * pad for text, _ in links]
    x = right - sum(widths) - gap * (len(links) - 1)
    for (text, url), width in zip(links, widths, strict=True):
        linkedin = text == "LinkedIn"
        pdf.set_fill_color(*(LINKEDIN if linkedin else WHITE))
        pdf.set_text_color(*(WHITE if linkedin else INDIGO_DARK))
        pdf.set_xy(x, y)
        pdf.cell(width, height, safe(text), align="C", fill=True, link=url)
        x += width + gap


def _stat(
    pdf: FPDF,
    x: float,
    label: str,
    value: str,
    fill: tuple[int, int, int],
    color: tuple[int, int, int],
    width: float = 66,
) -> None:
    """A rounded stat card: small label, big value."""
    y = pdf.get_y()
    pdf.set_fill_color(*fill)
    pdf.rect(x, y, width, 20, style="F", round_corners=True)
    pdf.set_xy(x + 5, y + 3)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(width - 10, 4, label)
    pdf.set_xy(x + 5, y + 8)
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(*color)
    pdf.cell(width - 10, 9, safe(value))
    pdf.set_xy(x, y)
