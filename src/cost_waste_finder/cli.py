"""Command-line entry point: `cwf`."""

import boto3
import click
from botocore.exceptions import BotoCoreError
from dotenv import load_dotenv

from cost_waste_finder import __version__
from cost_waste_finder.report import render_markdown
from cost_waste_finder.scanner import scan as run_scan


def resolve_region(session: boto3.Session, region: str | None) -> str:
    """Return --region if given, else the AWS config default. Never hard-coded."""
    if region:
        return region
    if not session.region_name:
        raise click.UsageError(
            "No region set. Pass --region or set a default (aws configure / AWS_DEFAULT_REGION)."
        )
    return session.region_name


@click.group()
@click.version_option(__version__, prog_name="cwf")
def cli() -> None:
    """Find wasted AWS spend (read-only)."""


@cli.command()
@click.option("--region", help="AWS region to scan. Defaults to your AWS config region.")
def scan(region: str | None) -> None:
    """Scan an AWS account for wasted spend and print a Markdown report."""
    try:
        session = boto3.Session()
        region = resolve_region(session, region)
        findings = run_scan(session, region)
    except BotoCoreError as error:
        # e.g. no credentials, unknown profile, expired SSO token
        raise click.ClickException(f"AWS credentials problem: {error}") from error
    click.echo(render_markdown(findings, region), nl=False)


def main() -> None:
    # Optional local .env (gitignored). Variables already set in the shell win.
    load_dotenv(override=False)
    cli()
