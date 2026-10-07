"""`cwf web`: a small local page. Enter a company name, click Scan, see the waste report and
download it as a PDF. Python standard library only; meant for your own machine.
"""

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from cost_waste_finder.branding import Branding
from cost_waste_finder.html_report import format_scanned, page, report_body
from cost_waste_finder.models import Finding
from cost_waste_finder.pdf_report import render_pdf
from cost_waste_finder.pdf_report import report_title as pdf_title

# A scan takes no arguments and returns (regions, findings); it may raise on AWS errors.
ScanFunction = Callable[[], tuple[list[str], list[Finding]]]

MAX_NAME_LENGTH = 80
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}

WEB_CSS = """
.scan-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
  padding: 20px; margin: -52px 0 28px; position: relative;
  box-shadow: 0 10px 30px rgba(49, 46, 129, 0.12); }
.scan-card label { display: block; font-weight: 700; margin-bottom: 8px; }
form.scan { display: flex; gap: 10px; flex-wrap: wrap; }
form.scan input { flex: 1 1 260px; padding: 12px 14px; font: inherit; font-size: 16px;
  color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: 10px; }
form.scan input:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.hint { color: var(--muted); font-size: 13px; margin: 10px 0 0; }
.button { padding: 12px 22px; font: inherit; font-weight: 700; border-radius: 10px;
  cursor: pointer; border: none; background: var(--accent); color: #fff; text-decoration: none;
  display: inline-flex; align-items: center; gap: 8px; }
@media (prefers-color-scheme: dark) { .button { color: #1e1b4b; } }
.button:hover { filter: brightness(1.08); }
.button[disabled] { opacity: 0.7; cursor: wait; }
.report-head { display: flex; justify-content: space-between; align-items: end; gap: 16px;
  flex-wrap: wrap; margin: 8px 0 8px; }
.report-head h2 { margin: 0; font-size: 22px; letter-spacing: -0.01em; }
.report-head .meta { margin: 4px 0 0; }
.error { border: 1px solid #f04438; background: #fef3f2; color: #b42318; border-radius: 12px;
  padding: 12px 14px; margin-bottom: 20px; }
"""

# Only for the local page (never in the downloadable report): show progress while scanning.
SCAN_SCRIPT = """
document.querySelector("form.scan").addEventListener("submit", function () {
  var b = this.querySelector("button");
  b.disabled = true;
  b.textContent = "Scanning all regions... (up to a minute)";
});
"""


@dataclass
class Report:
    organization: str
    regions: list[str]
    findings: list[Finding]
    scanned_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class WebApp:
    """Holds the latest report. One scan at a time."""

    def __init__(self, scan: ScanFunction, branding: Branding | None = None) -> None:
        self.scan = scan
        self.branding = branding
        self.report: Report | None = None
        self.error: str | None = None
        self._lock = threading.Lock()

    def run_scan(self, organization: str) -> None:
        with self._lock:
            try:
                regions, findings = self.scan()
            except Exception as error:  # show any AWS/credentials problem on the page
                self.error = str(error) or error.__class__.__name__
                return
            self.report = Report(organization, regions, findings)
            self.error = None


def clean_name(raw: str) -> str:
    """Organization name: trimmed, single-line, at most MAX_NAME_LENGTH characters."""
    return re.sub(r"\s+", " ", raw).strip()[:MAX_NAME_LENGTH]


def file_stem(report: Report) -> str:
    """e.g. "example-client-aws-cost-waste-report-2026-10-07"."""
    slug = re.sub(r"[^a-z0-9]+", "-", report.organization.lower()).strip("-")
    prefix = f"{slug}-" if slug else ""
    return f"{prefix}aws-cost-waste-report-{report.scanned_at.date().isoformat()}"


def report_title(report: Report | None) -> str:
    return pdf_title(report.organization if report else "")


def home_page(app: WebApp) -> str:
    report = app.report
    name = escape(report.organization) if report else ""
    body = f"""
  <section class="scan-card">
    <form class="scan" method="post" action="/scan">
      <input id="organization" name="organization" maxlength="{MAX_NAME_LENGTH}"
        placeholder="Company name, e.g. Acme Pty Ltd" value="{name}" aria-label="Company name">
      <button class="button" type="submit">Scan</button>
    </form>
    <p class="hint">Read-only scan of every enabled region in this AWS account.</p>
  </section>"""
    if app.error:
        body += f'\n  <div class="error">Scan failed: {escape(app.error)}</div>'
    if report:
        body += f"""
  <div class="report-head">
    <div>
      <h2>{escape(report_title(report))}</h2>
      <p class="meta">Scanned: {format_scanned(report.scanned_at)}</p>
    </div>
    <a class="button" href="/report.pdf">&#11015; Download PDF</a>
  </div>{report_body(report.findings, report.regions)}"""
    return page(
        "AWS Cost Waste Audit",
        body,
        subtitle="Find unused and idle AWS resources and what they cost each month.",
        branding=app.branding,
        extra_css=WEB_CSS,
        script=SCAN_SCRIPT,
    )


def make_handler(app: WebApp, allowed_hosts: set[str]):
    class Handler(BaseHTTPRequestHandler):
        server_version = "cwf"

        def do_GET(self) -> None:
            if not self._host_ok():
                return
            path = urlsplit(self.path).path
            if path == "/":
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", home_page(app).encode())
            elif path == "/report.pdf" and app.report is None:
                self._redirect("/")
            elif path == "/report.pdf":
                pdf = render_pdf(
                    app.report.findings,
                    app.report.regions,
                    app.report.organization,
                    app.report.scanned_at,
                    branding=app.branding,
                )
                self._send(HTTPStatus.OK, "application/pdf", pdf, f"{file_stem(app.report)}.pdf")
            else:
                self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")

        def do_POST(self) -> None:
            if not self._host_ok() or not self._same_origin():
                return
            if urlsplit(self.path).path != "/scan":
                self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")
                return
            length = min(int(self.headers.get("Content-Length") or 0), 10_000)
            form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
            app.run_scan(clean_name(form.get("organization", [""])[0]))
            self._redirect("/")

        def _host_ok(self) -> bool:
            """Refuse requests for other host names (protects against DNS rebinding)."""
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
            if host in allowed_hosts:
                return True
            self._send(HTTPStatus.FORBIDDEN, "text/plain; charset=utf-8", b"Forbidden host")
            return False

        def _same_origin(self) -> bool:
            """Refuse form posts from other websites (CSRF)."""
            origin = self.headers.get("Origin")
            if origin is None or urlsplit(origin).netloc == self.headers.get("Host"):
                return True
            self._send(HTTPStatus.FORBIDDEN, "text/plain; charset=utf-8", b"Forbidden origin")
            return False

        def _redirect(self, location: str) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send(
            self, status: HTTPStatus, content_type: str, body: bytes, download: str | None = None
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            pass  # keep the terminal quiet

    return Handler


def make_server(
    scan: ScanFunction, host: str, port: int, branding: Branding | None = None
) -> ThreadingHTTPServer:
    allowed_hosts = LOCAL_HOSTS | ({host.lower()} if host not in ("0.0.0.0", "::") else set())
    app = WebApp(scan, branding)
    server = ThreadingHTTPServer((host, port), make_handler(app, allowed_hosts))
    server.app = app  # type: ignore[attr-defined]  # handy for tests
    return server
