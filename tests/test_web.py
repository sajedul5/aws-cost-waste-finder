import http.client
import threading
from urllib.parse import urlencode

import pytest

from cost_waste_finder.models import Finding
from cost_waste_finder.web import Report, clean_name, file_stem, make_server

REGIONS = ["ap-southeast-1", "ap-southeast-2"]


def findings() -> list[Finding]:
    return [
        Finding("idle-nat-gateway", "nat-0ccc3333dddd4444e", "ap-southeast-1", "idle", {}, 43.07),
        Finding("old-snapshot", "snap-0aaa1111bbbb2222c", "ap-southeast-2", "<b>old</b>", {}, 4.04),
    ]


@pytest.fixture
def server():
    """A real server on a free port, with a fake scan (no AWS)."""
    calls = []

    def fake_scan():
        calls.append(1)
        return REGIONS, findings()

    httpd = make_server(fake_scan, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    httpd.calls = calls
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def request(server, method: str, path: str, body: dict | None = None, headers: dict | None = None):
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    all_headers = {"Host": f"localhost:{port}"}
    data = None
    if body is not None:
        data = urlencode(body)
        all_headers["Content-Type"] = "application/x-www-form-urlencoded"
    all_headers.update(headers or {})
    conn.request(method, path, body=data, headers=all_headers)
    response = conn.getresponse()
    return response, response.read()


def test_home_page_has_form(server) -> None:
    response, body = request(server, "GET", "/")
    page = body.decode()

    assert response.status == 200
    assert 'name="organization"' in page
    assert 'aria-label="Company name"' in page
    assert "AWS Cost Waste Audit" in page
    assert ">Scan</button>" in page
    assert "Download PDF" not in page  # nothing scanned yet


def test_scan_then_report_and_downloads(server) -> None:
    response, _ = request(server, "POST", "/scan", {"organization": "  Example   Client "})
    assert response.status == 303
    assert server.calls == [1]

    _, body = request(server, "GET", "/")
    page = body.decode()
    assert "Example Client - AWS Cost Waste Report" in page
    assert "$47.11/mo" in page
    assert "Scanned: " in page and " UTC" in page
    assert "&lt;b&gt;old&lt;/b&gt;" in page  # escaped
    assert 'href="/report.pdf"' in page
    assert "Download HTML" not in page

    response, pdf = request(server, "GET", "/report.pdf")
    assert response.status == 200
    assert response.getheader("Content-Type") == "application/pdf"
    assert "example-client-aws-cost-waste-report-" in response.getheader("Content-Disposition")
    assert pdf.startswith(b"%PDF-")

    response, _ = request(server, "GET", "/report.html")
    assert response.status == 404  # PDF only


def test_downloads_before_scan_redirect_home(server) -> None:
    response, _ = request(server, "GET", "/report.pdf")
    assert response.status == 303
    assert response.getheader("Location") == "/"


def test_scan_error_is_shown(server) -> None:
    def failing_scan():
        raise RuntimeError("AWS credentials problem: no credentials")

    server.app.scan = failing_scan
    request(server, "POST", "/scan", {"organization": "X"})

    _, body = request(server, "GET", "/")
    assert "Scan failed: AWS credentials problem: no credentials" in body.decode()


def test_rejects_other_host_names(server) -> None:
    response, _ = request(server, "GET", "/", headers={"Host": "evil.example:8080"})
    assert response.status == 403


def test_rejects_cross_site_post(server) -> None:
    response, _ = request(
        server, "POST", "/scan", {"organization": "X"}, {"Origin": "https://evil.example"}
    )
    assert response.status == 403
    assert server.calls == []


def test_unknown_path(server) -> None:
    response, _ = request(server, "GET", "/nope")
    assert response.status == 404


def test_clean_name_and_file_stem() -> None:
    assert clean_name("  Acme\n  Pty  Ltd ") == "Acme Pty Ltd"
    assert len(clean_name("x" * 500)) == 80
    from datetime import UTC, datetime

    when = datetime(2026, 10, 7, 9, 32, tzinfo=UTC)
    assert file_stem(Report("Acme Pty Ltd", REGIONS, [], when)) == (
        "acme-pty-ltd-aws-cost-waste-report-2026-10-07"
    )
    assert file_stem(Report("", REGIONS, [], when)) == "aws-cost-waste-report-2026-10-07"


def test_branding_card_on_page() -> None:
    from cost_waste_finder.branding import Branding
    from cost_waste_finder.web import WebApp, home_page

    app = WebApp(lambda: (REGIONS, []), Branding("Jane Doe", linkedin_url="https://x.example/in/j"))
    page = home_page(app)
    assert 'class="brand"' in page
    assert 'href="https://x.example/in/j" target="_blank" rel="noopener noreferrer"' in page
