"""Command-line entry point: `cwf`."""

import boto3
import click
from dotenv import load_dotenv

from cost_waste_finder import __version__


def resolve_region(region: str | None) -> str:
    """Return --region if given, else the AWS config default. Never hard-coded."""
    if region:
        return region
    default = boto3.session.Session().region_name
    if not default:
        raise click.UsageError(
            "No region set. Pass --region or set a default (aws configure / AWS_DEFAULT_REGION)."
        )
    return default


@click.group()
@click.version_option(__version__, prog_name="cwf")
def cli() -> None:
    """Find wasted AWS spend (read-only)."""


@cli.command()
@click.option("--region", help="AWS region to scan. Defaults to your AWS config region.")
def scan(region: str | None) -> None:
    """Scan an AWS account for wasted spend."""
    region = resolve_region(region)
    click.echo(f"Scanning region {region} (no checks yet).")


def main() -> None:
    # Optional local .env (gitignored). Variables already set in the shell win.
    load_dotenv(override=False)
    cli()
