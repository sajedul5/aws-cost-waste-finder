from datetime import date

from cost_waste_finder.branding import Branding, load_branding
from cost_waste_finder.html_report import render_html

ENV = {
    "CWF_PREPARED_BY": " Jane Doe ",
    "CWF_PREPARED_BY_TITLE": "DevOps Engineer",
    "CWF_CONTACT_EMAIL": "jane@example.com",
    "CWF_LINKEDIN_URL": "https://www.linkedin.com/in/jane-doe/",
}


def test_load_branding_from_env() -> None:
    branding = load_branding(ENV)

    assert branding == Branding(
        "Jane Doe", "DevOps Engineer", "jane@example.com", "https://www.linkedin.com/in/jane-doe/"
    )
    assert branding.linkedin_label == "linkedin.com/in/jane-doe"


def test_no_name_means_no_branding() -> None:
    assert load_branding({"CWF_CONTACT_EMAIL": "x@example.com"}) is None


def test_only_https_links_are_used() -> None:
    branding = load_branding({"CWF_PREPARED_BY": "J", "CWF_LINKEDIN_URL": "javascript:alert(1)"})
    assert branding.linkedin_url == ""


def test_html_links_open_in_new_tab() -> None:
    page = render_html([], ["ap-southeast-1"], date(2026, 10, 7), "Acme", load_branding(ENV))

    assert "Prepared by" in page and "<strong>Jane Doe</strong>" in page
    assert '<a href="mailto:jane@example.com">' in page
    assert (
        '<a href="https://www.linkedin.com/in/jane-doe/" target="_blank" '
        'rel="noopener noreferrer">' in page
    )


def test_html_escapes_branding() -> None:
    page = render_html([], ["ap-southeast-1"], None, "Acme", Branding("<b>x</b>"))
    assert "<b>x</b>" not in page
    assert "&lt;b&gt;x&lt;/b&gt;" in page
