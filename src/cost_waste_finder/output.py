"""Picks the renderer for --format and writes the report to stdout or --output."""

from collections.abc import Callable
from datetime import date
from pathlib import Path

from cost_waste_finder.html_report import render_html
from cost_waste_finder.models import Finding
from cost_waste_finder.report import render_csv, render_json, render_markdown

Renderer = Callable[[list[Finding], list[str], date | None], str]

RENDERERS: dict[str, Renderer] = {
    "markdown": render_markdown,
    "csv": render_csv,
    "json": render_json,
    "html": render_html,
}


def render(
    findings: list[Finding], regions: list[str], fmt: str, scanned_on: date | None = None
) -> str:
    return RENDERERS[fmt](findings, regions, scanned_on)


def write_report(text: str, path: Path) -> None:
    """Write the report, creating the folder if needed (e.g. reports/)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
