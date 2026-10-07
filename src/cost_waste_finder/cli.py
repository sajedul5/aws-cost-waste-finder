"""Command-line entry point: `cwf`."""

import functools
from pathlib import Path

import boto3
import click
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

from cost_waste_finder import __version__
from cost_waste_finder.billing import COST_PER_CALL_USD, get_bill_summary
from cost_waste_finder.billing_report import BILL_RENDERERS
from cost_waste_finder.config import Thresholds
from cost_waste_finder.dashboard import render_dashboard
from cost_waste_finder.models import BillSummary
from cost_waste_finder.output import RENDERERS, render, write_report
from cost_waste_finder.scanner import enabled_regions, scan_regions
from cost_waste_finder.session import make_session

DEFAULTS = Thresholds()


def resolve_region(session: boto3.Session, region: str | None) -> str:
    """Return --region if given, else the AWS config default. Never hard-coded."""
    if region:
        return region
    if not session.region_name:
        raise click.UsageError(
            "No region set. Pass --region or set a default (aws configure / AWS_DEFAULT_REGION)."
        )
    return session.region_name


# --- shared options --------------------------------------------------------------------------

ROLE_OPTIONS = [
    click.option(
        "--role-arn", help="Read-only IAM role to assume in a client account (see docs/iam.md)."
    ),
    click.option("--external-id", help="External ID the client set on that role's trust policy."),
]

THRESHOLD_OPTIONS = [
    click.option(
        "--lookback-days",
        type=click.IntRange(min=1),
        default=DEFAULTS.lookback_days,
        show_default=True,
        help="Days of CloudWatch history for the idle checks.",
    ),
    click.option(
        "--cpu-threshold",
        type=float,
        default=DEFAULTS.cpu_percent,
        show_default=True,
        help="Idle EC2: average CPU % below this.",
    ),
    click.option(
        "--network-threshold-mb",
        type=float,
        default=DEFAULTS.network_mb_per_day,
        show_default=True,
        help="Idle EC2: network in + out MB/day below this.",
    ),
    click.option(
        "--nat-threshold-gb",
        type=float,
        default=DEFAULTS.nat_gb,
        show_default=True,
        help="Idle NAT Gateway: total GB sent over the lookback below this.",
    ),
    click.option(
        "--lb-requests-threshold",
        type=int,
        default=DEFAULTS.lb_requests,
        show_default=True,
        help="Idle load balancer: total requests/new flows over the lookback below this.",
    ),
    click.option(
        "--snapshot-age-days",
        type=click.IntRange(min=1),
        default=DEFAULTS.snapshot_age_days,
        show_default=True,
        help="Old snapshot: older than this many days.",
    ),
    click.option(
        "--stopped-days",
        type=click.IntRange(min=1),
        default=DEFAULTS.stopped_days,
        show_default=True,
        help="Stopped EC2: stopped longer than this many days.",
    ),
]


def add_options(options):
    def decorator(func):
        for option in reversed(options):
            func = option(func)
        return func

    return decorator


def threshold_options(func):
    """Add the threshold options and pass them to the command as one `thresholds` argument."""

    @functools.wraps(func)
    def wrapper(
        *args,
        lookback_days,
        cpu_threshold,
        network_threshold_mb,
        nat_threshold_gb,
        lb_requests_threshold,
        snapshot_age_days,
        stopped_days,
        **kwargs,
    ):
        thresholds = Thresholds(
            lookback_days=lookback_days,
            cpu_percent=cpu_threshold,
            network_mb_per_day=network_threshold_mb,
            nat_gb=nat_threshold_gb,
            lb_requests=lb_requests_threshold,
            snapshot_age_days=snapshot_age_days,
            stopped_days=stopped_days,
        )
        return func(*args, thresholds=thresholds, **kwargs)

    return add_options(THRESHOLD_OPTIONS)(wrapper)


# --- commands --------------------------------------------------------------------------------


@click.group()
@click.version_option(__version__, prog_name="cwf")
def cli() -> None:
    """Find wasted AWS spend (read-only)."""


@cli.command()
@click.option("--region", help="AWS region to scan. Defaults to your AWS config region.")
@click.option("--all-regions", is_flag=True, help="Scan every region enabled for the account.")
@add_options(ROLE_OPTIONS)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(list(RENDERERS)),
    default="markdown",
    show_default=True,
    help="Report format.",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the report to this file (e.g. reports/scan.html) instead of the screen.",
)
@threshold_options
def scan(
    region: str | None,
    all_regions: bool,
    role_arn: str | None,
    external_id: str | None,
    fmt: str,
    output: Path | None,
    thresholds: Thresholds,
) -> None:
    """Scan an AWS account for wasted spend and print a report."""
    if region and all_regions:
        raise click.UsageError("Use either --region or --all-regions, not both.")
    session = open_session(role_arn, external_id)
    regions, findings = run_scan(session, region, all_regions, thresholds)
    emit(render(findings, regions, fmt), output)


@cli.command()
@add_options(ROLE_OPTIONS)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(list(BILL_RENDERERS)),
    default="markdown",
    show_default=True,
    help="Report format.",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the report to this file instead of the screen.",
)
def bill(role_arn: str | None, external_id: str | None, fmt: str, output: Path | None) -> None:
    """3-month bill trend per service (Cost Explorer: about $0.01 per API call)."""
    session = open_session(role_arn, external_id)
    emit(BILL_RENDERERS[fmt](run_bill(session)), output)


@cli.command()
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="HTML file to write, e.g. reports/dashboard.html.",
)
@click.option("--title", help='Name shown on the dashboard, e.g. "Client A". No account IDs.')
@click.option("--region", help="Only this region. Default: every enabled region.")
@click.option("--no-bill", is_flag=True, help="Skip the bill trend (no Cost Explorer charge).")
@add_options(ROLE_OPTIONS)
@threshold_options
def dashboard(
    output: Path,
    title: str | None,
    region: str | None,
    no_bill: bool,
    role_arn: str | None,
    external_id: str | None,
    thresholds: Thresholds,
) -> None:
    """One HTML page: 3-month bill trend, waste findings and recommended actions."""
    session = open_session(role_arn, external_id)
    regions, findings = run_scan(session, region, not region, thresholds)
    summary = None if no_bill else run_bill(session)
    emit(render_dashboard(findings, regions, summary, title), output)


# --- helpers ---------------------------------------------------------------------------------


def open_session(role_arn: str | None, external_id: str | None) -> boto3.Session:
    if external_id and not role_arn:
        raise click.UsageError("--external-id needs --role-arn.")
    try:
        return make_session(role_arn, external_id)
    except ClientError as error:
        details = error.response["Error"]
        raise click.ClickException(
            f"Could not assume role: {details['Code']}: {details.get('Message', '')}. "
            "Check the role's trust policy and external ID (docs/iam.md)."
        ) from error
    except BotoCoreError as error:
        raise click.ClickException(f"AWS credentials problem: {error}") from error


def run_scan(session: boto3.Session, region: str | None, all_regions: bool, thresholds: Thresholds):
    try:
        if all_regions:
            # DescribeRegions works from any region; prefer the configured one.
            regions = enabled_regions(session, session.region_name or "us-east-1")
        else:
            regions = [resolve_region(session, region)]
        return regions, scan_regions(session, regions, thresholds)
    except BotoCoreError as error:
        # e.g. no credentials, unknown profile, expired SSO token
        raise click.ClickException(f"AWS credentials problem: {error}") from error


def run_bill(session: boto3.Session) -> BillSummary:
    try:
        summary = get_bill_summary(session)
    except ClientError as error:
        details = error.response["Error"]
        raise click.ClickException(
            f"Cost Explorer error: {details['Code']}: {details.get('Message', '')}. "
            "Cost Explorer must be enabled, and you need ce:GetCostAndUsage and "
            "ce:GetCostForecast (docs/iam.md)."
        ) from error
    except BotoCoreError as error:
        raise click.ClickException(f"AWS credentials problem: {error}") from error
    calls = summary.api_calls
    click.echo(f"Cost Explorer calls: {calls} (~${calls * COST_PER_CALL_USD:.2f})", err=True)
    return summary


def emit(text: str, output: Path | None) -> None:
    if output:
        write_report(text, output)
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(text, nl=False)


def main() -> None:
    # Optional local .env (gitignored). Variables already set in the shell win.
    load_dotenv(override=False)
    cli()
