import boto3
import pytest
from botocore.exceptions import ClientError
from click.testing import CliRunner
from moto import mock_aws

from cost_waste_finder.cli import cli
from cost_waste_finder.session import ROLE_SESSION_NAME, make_session

ROLE_ARN = "arn:aws:iam::123456789012:role/CwfReadOnly"  # moto's fake account


def test_without_role_uses_default_chain() -> None:
    # conftest sets the default chain to fake "testing" keys; no STS call is made.
    assert make_session().get_credentials().access_key == "testing"


@mock_aws
def test_assumes_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-1")
    session = make_session(ROLE_ARN)

    credentials = session.get_credentials()
    assert credentials.access_key != "testing"
    assert credentials.token
    assert session.region_name == "ap-southeast-1"
    identity = session.client("sts").get_caller_identity()
    assert f"assumed-role/CwfReadOnly/{ROLE_SESSION_NAME}" in identity["Arn"]


def test_passes_external_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    class FakeSts:
        def assume_role(self, **params):
            seen.update(params)
            return {
                "Credentials": {"AccessKeyId": "a", "SecretAccessKey": "b", "SessionToken": "c"}
            }

    monkeypatch.setattr(boto3.Session, "client", lambda self, *a, **k: FakeSts())
    make_session(ROLE_ARN, external_id="my-external-id")

    assert seen["ExternalId"] == "my-external-id"
    assert seen["RoleArn"] == ROLE_ARN
    assert seen["DurationSeconds"] == 3600


def test_cli_explains_assume_role_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(role_arn, external_id):
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "not authorized"}}, "AssumeRole"
        )

    monkeypatch.setattr("cost_waste_finder.cli.make_session", denied)
    result = CliRunner().invoke(cli, ["scan", "--region", "ap-southeast-1", "--role-arn", ROLE_ARN])

    assert result.exit_code != 0
    assert "Could not assume role: AccessDenied: not authorized" in result.output
    assert "Traceback" not in result.output


def test_external_id_needs_role_arn() -> None:
    result = CliRunner().invoke(cli, ["scan", "--region", "ap-southeast-1", "--external-id", "x"])
    assert result.exit_code != 0
    assert "--external-id needs --role-arn" in result.output


@mock_aws
def test_clients_use_adaptive_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-1")
    for session in (make_session(), make_session(ROLE_ARN)):
        assert session.client("ec2").meta.config.retries["mode"] == "adaptive"
