from datetime import date

from cost_waste_finder.models import Finding
from cost_waste_finder.pdf_report import render_pdf, safe

DAY = date(2026, 10, 7)
REGIONS = ["ap-southeast-1"]


def findings() -> list[Finding]:
    return [
        Finding("old-snapshot", "snap-0aaa1111bbbb2222c", "ap-southeast-1", "old", {}, 4.04),
        Finding("idle-nat-gateway", "nat-0ccc3333dddd4444e", "ap-southeast-1", "idle", {}, 43.07),
        Finding("unattached-eip", "eipalloc-0f1e2d3c", "ap-southeast-1", "unused", {}, None),
    ]


def text(pdf: bytes) -> str:
    return pdf.decode("latin-1")


def test_pdf_has_title_total_and_rows() -> None:
    pdf = render_pdf(findings(), REGIONS, "Example Client", DAY, compress=False)
    content = text(pdf)

    assert pdf.startswith(b"%PDF-")
    assert "Example Client - AWS Cost Waste Report" in content
    assert "Potential savings per month" in content
    assert "($47.11) Tj" in content
    assert "$565.32" in content  # per year
    assert "Scanned: 2026-10-07" in content
    assert content.index("nat-0ccc3333dddd4444e") < content.index("snap-0aaa1111bbbb2222c")
    assert "have no price (n/a)" not in content  # parentheses are escaped in PDF text
    assert "have no price" in content


def test_pdf_without_findings() -> None:
    assert "No waste found" in text(render_pdf([], REGIONS, "", DAY, compress=False))


def test_pdf_many_findings_spans_pages() -> None:
    pdf = render_pdf(findings() * 40, REGIONS, "Big", DAY, compress=False)
    assert "Page 2" in text(pdf)


def test_non_latin_names_do_not_crash() -> None:
    cleaned = safe("Café ব্র্যাক")
    assert cleaned.startswith("Café ?")
    cleaned.encode("latin-1")  # fits the built-in PDF fonts
    assert render_pdf(findings(), REGIONS, "ব্র্যাক", DAY).startswith(b"%PDF-")


def test_prepared_by_block_with_links() -> None:
    from cost_waste_finder.branding import Branding

    branding = Branding(
        name="Jane Doe",
        title="DevOps Engineer",
        email="jane@example.com",
        linkedin_url="https://www.linkedin.com/in/jane-doe/",
    )
    content = text(render_pdf(findings(), REGIONS, "Acme", DAY, compress=False, branding=branding))

    assert "Prepared by" in content
    assert "Jane Doe" in content and "DevOps Engineer" in content
    assert "/URI (mailto:jane@example.com)" in content
    assert "/URI (https://www.linkedin.com/in/jane-doe/)" in content
    assert "(LinkedIn) Tj" in content  # shown as a word, not the URL
    assert "linkedin.com/in/jane-doe) Tj" not in content
    assert "/Author (Jane Doe)" in content


def test_no_prepared_by_without_branding() -> None:
    assert "Prepared by" not in text(render_pdf(findings(), REGIONS, "Acme", DAY, compress=False))
