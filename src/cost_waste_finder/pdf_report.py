"""PDF version of the waste report, to share with a client. Built with fpdf2 (pure Python).

Same look as the HTML report: AWS-console-like navy bar and orange line, plain documentation-style
summary and table. No AWS logo: this is not an official AWS document.
"""

from datetime import date, datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

from cost_waste_finder.branding import Branding
from cost_waste_finder.html_report import PRODUCT, format_scanned
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

NAVY = (35, 47, 62)  # #232f3e
ORANGE = (255, 153, 0)  # #ff9900
LINK = (9, 114, 211)  # #0972d3
INFO_BG = (242, 248, 253)
MONEY = (3, 127, 12)  # #037f0c
TEXT = (0, 7, 22)
MUTED = (95, 107, 122)
BORDER = (233, 235, 237)
HEAD_BG = (250, 250, 250)
WHITE = (255, 255, 255)

BAR_HEIGHT = 12  # mm, navy top bar
COLUMN_WIDTHS = (36, 52, 30, 120, 29)  # mm on landscape A4 (277 mm usable)


def safe(text: str) -> str:
    """The built-in PDF fonts only cover Latin-1; replace anything else instead of failing."""
    return text.encode("latin-1", "replace").decode("latin-1")


def report_title(organization: str) -> str:
    return f"{organization} - AWS Cost Waste Report" if organization else "AWS Cost Waste Report"


class ReportPDF(FPDF):
    def header(self) -> None:
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, BAR_HEIGHT, style="F")
        self.set_fill_color(*ORANGE)
        self.rect(0, BAR_HEIGHT, self.w, 1, style="F")
        self.set_xy(self.l_margin, 3.5)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*WHITE)
        self.cell(0, 5, PRODUCT)
        self.set_y(BAR_HEIGHT + 8)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_draw_color(*BORDER)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
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

    pdf.set_text_color(*TEXT)
    pdf.set_font("Helvetica", "B", 20)
    pdf.multi_cell(0, 9, safe(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, f"Scanned: {format_scanned(scanned_on)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    if branding:
        _prepared_by(pdf, branding)

    _summary(pdf, findings, regions)
    if not findings:
        return bytes(pdf.output())

    total = total_savings(findings)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*TEXT)
    pdf.cell(0, 8, "Findings", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.set_draw_color(*BORDER)
    pdf.set_fill_color(*WHITE)  # rows stay white; only the heading is grey
    pdf.set_text_color(*TEXT)
    pdf.set_font("Helvetica", size=8.5)
    heading = FontFace(emphasis="BOLD", color=MUTED, fill_color=HEAD_BG)
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
                    safe(report_reason(f)),
                    format_cost(f.monthly_cost),
                ]
            )
        total_row = table.row(style=FontFace(emphasis="BOLD", color=MONEY))
        total_row.cell(f"Total ({plural(len(findings), 'finding')})", colspan=4)
        total_row.cell(format_cost(total))

    notes = []
    unpriced = sum(1 for f in findings if f.monthly_cost is None)
    if unpriced:
        notes.append(f"{unpriced} finding(s) have no price (n/a) and are not in the total.")
    if note := verify_note(findings):
        notes.append(note)
    pdf.set_text_color(*MUTED)
    for text in notes:
        pdf.ln(3)
        pdf.multi_cell(0, 5, safe(text), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _prepared_by(pdf: FPDF, branding: Branding) -> None:
    """Blue info note: name, title, clickable email and LinkedIn."""
    x, y, width = pdf.l_margin, pdf.get_y(), pdf.epw
    height = 22 if branding.title else 17
    pdf.set_fill_color(*INFO_BG)
    pdf.set_draw_color(*LINK)
    pdf.rect(x, y, width, height, style="DF", round_corners=True, corner_radius=2)
    pdf.set_fill_color(*LINK)
    pdf.rect(x, y, 1.5, height, style="F")

    left = x + 7
    pdf.set_xy(left, y + 3)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 4, "Prepared by", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(left)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*TEXT)
    pdf.cell(0, 6, safe(branding.name), new_x="LMARGIN", new_y="NEXT")
    if branding.title:
        pdf.set_x(left)
        pdf.set_font("Helvetica", size=9)
        pdf.set_text_color(*MUTED)
        title = safe(branding.title.replace("|", "·"))  # "|" looks like "I" in Helvetica
        pdf.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")

    # links on the right, blue like documentation links
    links = []
    if branding.email:
        links.append((branding.email, f"mailto:{branding.email}"))
    if branding.linkedin_url:
        links.append(("LinkedIn", branding.linkedin_url))
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(*LINK)
    link_y = y + height / 2 - 2.5
    right = x + width - 6
    for text, url in reversed(links):
        w = pdf.get_string_width(safe(text)) + 1
        right -= w
        pdf.set_xy(right, link_y)
        pdf.cell(w, 5, safe(text), link=url)
        right -= 8
    pdf.set_xy(x, y + height + 5)


def _summary(pdf: FPDF, findings: list[Finding], regions: list[str]) -> None:
    """Bordered "Summary" box: savings per month (green), per year, findings, regions."""
    x, y, width = pdf.l_margin, pdf.get_y(), pdf.epw
    total = total_savings(findings)
    if findings:
        items = [
            ("Potential savings per month", format_cost(total), MONEY),
            ("Per year", format_cost(total * 12), TEXT),
            ("Findings", str(len(findings)), TEXT),
        ]
    else:
        items = [("Result", "No waste found", MONEY)]

    pdf.set_font("Helvetica", size=8)
    regions_text = safe(regions_label(regions))
    regions_lines = len(pdf.multi_cell(width - 12, 4, regions_text, dry_run=True, output="LINES"))
    height = 34 + regions_lines * 4
    pdf.set_draw_color(*BORDER)
    pdf.rect(x, y, width, height, style="D", round_corners=True, corner_radius=2)
    pdf.set_xy(x + 6, y + 3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*TEXT)
    pdf.cell(0, 7, "Summary")
    pdf.line(x, y + 12, x + width, y + 12)

    column = (width - 12) / 3
    for index, (label, value, color) in enumerate(items):
        cx = x + 6 + index * column
        pdf.set_xy(cx, y + 15)
        pdf.set_font("Helvetica", size=8.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(column, 4, label)
        pdf.set_xy(cx, y + 20)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*color)
        pdf.cell(column, 8, safe(value))

    pdf.set_xy(x + 6, y + 31)
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(width - 12, 4, regions_text)
    pdf.set_xy(x, y + height + 6)
