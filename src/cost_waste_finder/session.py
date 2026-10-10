"""Builds the boto3 session: your own credentials, or an assumed read-only client role."""

import boto3
import botocore.session
from botocore.config import Config

# Adaptive retries back off when AWS throttles us (the idle checks make several CloudWatch calls
# per resource, so large accounts can hit rate limits).
RETRY_CONFIG = Config(retries={"mode": "adaptive", "max_attempts": 10})

ROLE_SESSION_NAME = "cwf-scan"
ROLE_DURATION_SECONDS = 3600


def make_session(role_arn: str | None = None, external_id: str | None = None) -> boto3.Session:
    """Default credential chain, or temporary credentials from sts:AssumeRole when role_arn is set.

    Raises botocore ClientError if the role can't be assumed (e.g. AccessDenied).
    """
    base = _with_retries()
    if not role_arn:
        return base

    params = {
        "RoleArn": role_arn,
        "RoleSessionName": ROLE_SESSION_NAME,
        "DurationSeconds": ROLE_DURATION_SECONDS,
    }
    if external_id:
        params["ExternalId"] = external_id
    # STS is global; any region works. Use the configured one so it stays in your region.
    sts = base.client("sts", region_name=base.region_name or "us-east-1")
    credentials = sts.assume_role(**params)["Credentials"]
    return _with_retries(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=base.region_name,
    )


def _with_retries(**kwargs) -> boto3.Session:
    """A boto3 Session whose clients all use RETRY_CONFIG."""
    core = botocore.session.get_session()
    core.set_default_client_config(RETRY_CONFIG)
    return boto3.Session(botocore_session=core, **kwargs)
