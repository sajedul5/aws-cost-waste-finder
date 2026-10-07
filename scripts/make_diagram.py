"""Draws the architecture diagram in draw.io style.

Writes docs/architecture.drawio (open and edit at https://app.diagrams.net) and
docs/images/architecture.svg (turned into architecture.png for the README).
Run: python scripts/make_diagram.py
"""

from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIDTH, HEIGHT = 1400, 715

# draw.io default palette: (fill, stroke)
BLUE = ("#dae8fc", "#6c8ebf")
ORANGE = ("#ffe6cc", "#d79b00")
GREEN = ("#d5e8d4", "#82b366")
PURPLE = ("#e1d5e7", "#9673a6")
YELLOW = ("#fff2cc", "#d6b656")
GREY = ("#f5f5f5", "#666666")
RED = ("#f8cecc", "#b85450")

EC2_LABEL = "EC2 / EBS\nDescribe instances, volumes,\nsnapshots, images, addresses, NAT"
ELB_LABEL = "Elastic Load Balancing\nDescribe load balancers,\ntarget groups, target health"
CW_LABEL = "CloudWatch\nGetMetricStatistics (14 days CPU,\nnetwork, NAT bytes, requests)"
NEVER_LABEL = "Never used\nno create / modify / delete\nno Cost Explorer (no per-call charge)"

# Groups: id, label, x, y, w, h, (fill, stroke)
GROUPS = [
    ("you", "Your computer", 30, 90, 300, 600, ("#ffffff", "#999999")),
    ("cwf", "cwf (Docker container or pipx)", 380, 90, 460, 600, ("#fafafa", "#666666")),
    ("aws", "AWS account (read-only IAM user or role)", 890, 90, 480, 600, ("#ffffff", "#ff9900")),
]

# Boxes: id, label (\n = new line), x, y, w, h, colours
BOXES = [
    ("browser", "Browser\nhttp://localhost:8080\nCompany name + Scan", 60, 150, 240, 90, BLUE),
    ("terminal", "Terminal\ncwf scan --all-regions", 60, 290, 240, 70, BLUE),
    ("env", ".env\nAWS access key + secret\n(never in the image or Git)", 60, 410, 240, 90, YELLOW),
    ("outputs", "Reports\nPDF  ·  web page\nMarkdown · CSV · JSON · HTML", 60, 570, 240, 90, GREEN),
    ("web", "Web page / CLI\nweb.py · cli.py", 420, 150, 380, 60, BLUE),
    (
        "scanner",
        "Scanner\nall enabled regions in parallel (8 at a time)",
        420,
        260,
        380,
        60,
        PURPLE,
    ),
    (
        "checks",
        "8 waste checks\nunattached EBS · old snapshots · unused Elastic IPs\n"
        "gp2 → gp3 · idle EC2 · idle NAT Gateway\nidle load balancer · stopped EC2",
        420,
        360,
        380,
        100,
        PURPLE,
    ),
    ("pricing", "Pricing\nmonthly cost per finding (cached)", 420, 500, 380, 60, ORANGE),
    ("render", "Report builder\nsorted by savings · total · PDF", 420, 600, 380, 60, GREEN),
    # AWS column: (id, label, x, y, w, h, colours)
    ("sts", "STS (optional)\nAssumeRole into a client's read-only role", 920, 150, 420, 60, GREY),
    ("ec2", EC2_LABEL, 920, 228, 420, 76, ORANGE),
    ("elb", ELB_LABEL, 920, 320, 420, 76, ORANGE),
    ("cw", CW_LABEL, 920, 412, 420, 76, ORANGE),
    (
        "price",
        "AWS Pricing API (us-east-1)\nGetProducts: on-demand USD prices",
        920,
        500,
        420,
        60,
        GREY,
    ),
    ("never", NEVER_LABEL, 920, 590, 420, 76, RED),
]

# Arrows: from, to, label
EDGES = [
    ("browser", "web", "Scan"),
    ("terminal", "web", ""),
    ("env", "scanner", "credentials"),
    ("web", "scanner", ""),
    ("scanner", "checks", ""),
    ("checks", "pricing", "findings"),
    ("pricing", "render", ""),
    ("render", "outputs", "Download PDF"),
    ("checks", "ec2", "read-only"),
    ("checks", "elb", ""),
    ("checks", "cw", ""),
    ("pricing", "price", ""),
    ("web", "sts", "--role-arn"),
]


def box(box_id: str) -> tuple:
    return next(b for b in BOXES if b[0] == box_id)


def anchor(src: tuple, dst: tuple) -> tuple[tuple[float, float], tuple[float, float]]:
    """Connect the facing sides: left/right when side by side, else top/bottom."""
    _, _, sx, sy, sw, sh, _ = src
    _, _, dx, dy, dw, dh, _ = dst
    if sx + sw <= dx:  # dst on the right
        return (sx + sw, sy + sh / 2), (dx, dy + dh / 2)
    if dx + dw <= sx:  # dst on the left
        return (sx, sy + sh / 2), (dx + dw, dy + dh / 2)
    if sy + sh <= dy:  # dst below
        return (sx + sw / 2, sy + sh), (dx + dw / 2, dy)
    return (sx + sw / 2, sy), (dx + dw / 2, dy + dh)


def svg() -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="Helvetica, Arial, sans-serif">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" '
        'markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        'fill="#333"/></marker></defs>',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>',
        '<text x="700" y="48" text-anchor="middle" font-size="26" font-weight="bold" '
        'fill="#232f3e">AWS Cost Waste Finder - architecture</text>',
    ]
    for _, label, x, y, w, h, (fill, stroke) in GROUPS:
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="2" stroke-dasharray="8 5"/>'
            f'<text x="{x + 14}" y="{y + 26}" font-size="15" font-weight="bold" '
            f'fill="#333">{escape(label)}</text>'
        )
    for src_id, dst_id, label in EDGES:
        (x1, y1), (x2, y2) = anchor(box(src_id), box(dst_id))
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#333" stroke-width="1.6" '
            'marker-end="url(#arrow)"/>'
        )
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            width = len(label) * 7.2 + 8
            parts.append(
                f'<rect x="{mx - width / 2}" y="{my - 10}" width="{width}" '
                f'height="18" fill="#ffffff"/><text x="{mx}" y="{my + 4}" text-anchor="middle" '
                f'font-size="12" fill="#555">{escape(label)}</text>'
            )
    for _, label, x, y, w, h, (fill, stroke) in BOXES:
        lines = label.split("\n")
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.6"/>'
        )
        top = y + h / 2 - (len(lines) - 1) * 9
        for index, line in enumerate(lines):
            weight = ' font-weight="bold"' if index == 0 else ""
            parts.append(
                f'<text x="{x + w / 2}" y="{top + index * 18 + 5}" text-anchor="middle" '
                f'font-size="{14 if index == 0 else 12}"{weight} fill="#1a1a1a">'
                f"{escape(line)}</text>"
            )
    parts.append("</svg>")
    return "\n".join(parts)


def drawio() -> str:
    """Same diagram as an editable draw.io (diagrams.net) file."""
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for gid, label, x, y, w, h, (fill, stroke) in GROUPS:
        style = (
            f"rounded=1;arcSize=3;dashed=1;fillColor={fill};strokeColor={stroke};strokeWidth=2;"
            "verticalAlign=top;align=left;spacingLeft=10;fontStyle=1;fontSize=15;"
        )
        cells.append(
            f'<mxCell id="{gid}" value="{escape(label)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
    for bid, label, x, y, w, h, (fill, stroke) in BOXES:
        lines = label.split("\n")
        value = f"<b>{escape(lines[0])}</b><br>" + "<br>".join(escape(line) for line in lines[1:])
        style = (
            f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};fontSize=12;"
        )
        cells.append(
            f'<mxCell id="{bid}" value="{escape(value)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
    for index, (src, dst, label) in enumerate(EDGES):
        cells.append(
            f'<mxCell id="e{index}" value="{escape(label)}" '
            'style="endArrow=classic;html=1;fontSize=11;" edge="1" parent="1" '
            f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>'
        )
    return (
        '<mxfile host="cwf"><diagram name="architecture">'
        f'<mxGraphModel dx="{WIDTH}" dy="{HEIGHT}" grid="1" gridSize="10" page="0">'
        f"<root>{''.join(cells)}</root></mxGraphModel></diagram></mxfile>\n"
    )


if __name__ == "__main__":
    (ROOT / "docs" / "images").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "images" / "architecture.svg").write_text(svg(), encoding="utf-8")
    (ROOT / "docs" / "architecture.drawio").write_text(drawio(), encoding="utf-8")
    print("wrote docs/images/architecture.svg and docs/architecture.drawio")
