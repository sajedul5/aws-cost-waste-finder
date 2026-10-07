"""Command-line entry point: `cwf`."""

import boto3
import click
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

from cost_waste_finder import __version__
from cost_waste_finder.config import Thresholds
from cost_waste_finder.report import render_markdown
from cost_waste_finder.scanner import enabled_regions, scan_regions
from cost_waste_finder.session import make_session


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


DEFAULTS = Thresholds()


@cli.command()
@click.option("--region", help="AWS region to scan. Defaults to your AWS config region.")
@click.option("--all-regions", is_flag=True, help="Scan every region enabled for the account.")
@click.option(
    "--role-arn",
    help="Read-only IAM role to assume in a client account (see docs/iam.md).",
)
@click.option("--external-id", help="External ID the client set on that role's trust policy.")
@click.option(
    "--lookback-days",
    type=click.IntRange(min=1),
    default=DEFAULTS.lookback_days,
    show_default=True,
    help="Days of CloudWatch history for the idle checks.",
)
@click.option(
    "--cpu-threshold",
    type=float,
    default=DEFAULTS.cpu_percent,
    show_default=True,
    help="Idle EC2: average CPU % below this.",
)
@click.option(
    "--network-threshold-mb",
    type=float,
    default=DEFAULTS.network_mb_per_day,
    show_default=True,
    help="Idle EC2: network in + out MB/day below this.",
)
@click.option(
    "--nat-threshold-gb",
    type=float,
    default=DEFAULTS.nat_gb,
    show_default=True,
    help="Idle NAT Gateway: total GB sent over the lookback below this.",
)
@click.option(
    "--lb-requests-threshold",
    type=int,
    default=DEFAULTS.lb_requests,
    show_default=True,
    help="Idle load balancer: total requests/new flows over the lookback below this.",
)
@click.option(
    "--snapshot-age-days",
    type=click.IntRange(min=1),
    default=DEFAULTS.snapshot_age_days,
    show_default=True,
    help="Old snapshot: older than this many days.",
)
@click.option(
    "--stopped-days",
    type=click.IntRange(min=1),
    default=DEFAULTS.stopped_days,
    show_default=True,
    help="Stopped EC2: stopped longer than this many days.",
)
def scan(
    region: str | None,
    all_regions: bool,
    role_arn: str | None,
    external_id: str | None,
    lookback_days: int,
    cpu_threshold: float,
    network_threshold_mb: float,
    nat_threshold_gb: float,
    lb_requests_threshold: int,
    snapshot_age_days: int,
    stopped_days: int,
) -> None:
    """Scan an AWS account for wasted spend and print a Markdown report."""
    thresholds = Thresholds(
        lookback_days=lookback_days,
        cpu_percent=cpu_threshold,
        network_mb_per_day=network_threshold_mb,
        nat_gb=nat_threshold_gb,
        lb_requests=lb_requests_threshold,
        snapshot_age_days=snapshot_age_days,
        stopped_days=stopped_days,
    )
    if region and all_regions:
        raise click.UsageError("Use either --region or --all-regions, not both.")
    if external_id and not role_arn:
        raise click.UsageError("--external-id needs --role-arn.")
    try:
        session = assume_role_or_exit(role_arn, external_id)
        if all_regions:
            # DescribeRegions works from any region; prefer the configured one.
            regions = enabled_regions(session, session.region_name or "us-east-1")
        else:
            regions = [resolve_region(session, region)]
        findings = scan_regions(session, regions, thresholds)
    except BotoCoreError as error:
        # e.g. no credentials, unknown profile, expired SSO token
        raise click.ClickException(f"AWS credentials problem: {error}") from error
    click.echo(render_markdown(findings, regions), nl=False)


def assume_role_or_exit(role_arn: str | None, external_id: str | None) -> boto3.Session:
    try:
        return make_session(role_arn, external_id)
    except ClientError as error:
        details = error.response["Error"]
        raise click.ClickException(
            f"Could not assume role: {details['Code']}: {details.get('Message', '')}. "
            "Check the role's trust policy and external ID (docs/iam.md)."
        ) from error


def main() -> None:
    # Optional local .env (gitignored). Variables already set in the shell win.
    load_dotenv(override=False)
    cli()
