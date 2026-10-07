"""Builds the README samples from FAKE data (no AWS calls, no real resource IDs).

Writes examples/sample-report.md, examples/sample-report.pdf and docs/images/web-page.html
(screenshot it to web-page.png). "Prepared by" details come from CWF_* in your .env
(the email is left out, because these files are public).
Run: python scripts/make_samples.py
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from cost_waste_finder.branding import load_branding
from cost_waste_finder.models import Finding
from cost_waste_finder.pdf_report import render_pdf
from cost_waste_finder.report import render_markdown
from cost_waste_finder.web import Report, WebApp, home_page

ROOT = Path(__file__).resolve().parent.parent
COMPANY = "Example Client Pty Ltd"
SCANNED_AT = datetime(2026, 10, 7, 9, 32, tzinfo=UTC)
REGIONS = ["ap-south-1", "ap-southeast-1", "ap-southeast-2", "us-east-1"]

# Fake IDs; costs use real on-demand prices for those regions.
FINDINGS = [
    Finding(
        "idle-ec2",
        "i-0aaa1111bbbb2222c",
        "ap-southeast-2",
        "m5.xlarge running, avg CPU 1.2%, network 0.3 MB/day (14 days)",
        {},
        175.20,
    ),
    Finding(
        "unattached-ebs",
        "vol-0eee5555ffff6666a",
        "ap-south-1",
        "Unattached volume (status available), 500 GiB gp2",
        {},
        57.00,
    ),
    Finding(
        "idle-nat-gateway",
        "nat-0ccc3333dddd4444e",
        "ap-southeast-1",
        "NAT Gateway sent 0.02 GB in 14 days",
        {},
        43.07,
    ),
    Finding(
        "stopped-ec2",
        "i-0bbb7777cccc8888d",
        "ap-southeast-1",
        "t3.xlarge stopped 74 days, still paying for 2 volumes (300 GiB)",
        {},
        28.80,
    ),
    Finding(
        "gp2-to-gp3",
        "vol-0aaa2222bbbb3333c",
        "ap-southeast-2",
        "gp2 volume (1000 GiB) can be changed to gp3 with the same IOPS",
        {},
        24.00,
    ),
    Finding(
        "idle-load-balancer",
        "app/old-api/1a2b3c4d5e6f7a8b",
        "us-east-1",
        "ALB with no registered targets",
        {},
        16.43,
    ),
    Finding(
        "old-snapshot",
        "snap-0ddd9999eeee0000f",
        "ap-south-1",
        "Snapshot 260 days old, not used by any AMI, up to 80.72 GiB",
        {},
        4.04,
    ),
    Finding(
        "unattached-eip",
        "eipalloc-0f1e2d3c4b5a6978",
        "ap-southeast-1",
        "Elastic IP not associated with any instance or network interface",
        {},
        3.65,
    ),
]


def main() -> None:
    load_dotenv(ROOT / ".env")
    branding = load_branding()
    if branding:
        branding = replace(branding, email="")  # public samples: no email address
    examples = ROOT / "examples"
    examples.mkdir(exist_ok=True)

    (examples / "sample-report.md").write_text(
        render_markdown(FINDINGS, REGIONS, SCANNED_AT.date()), encoding="utf-8"
    )
    (examples / "sample-report.pdf").write_bytes(
        render_pdf(FINDINGS, REGIONS, COMPANY, SCANNED_AT, branding=branding)
    )
    app = WebApp(lambda: (REGIONS, FINDINGS), branding)
    app.report = Report(COMPANY, REGIONS, FINDINGS, SCANNED_AT)
    (ROOT / "docs" / "images" / "web-page.html").write_text(home_page(app), encoding="utf-8")
    print("wrote examples/sample-report.md, examples/sample-report.pdf, docs/images/web-page.html")


if __name__ == "__main__":
    main()
