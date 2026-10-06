import pytest


@pytest.fixture(autouse=True)
def fake_aws_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Make sure no test can reach a real AWS account or read local AWS config."""
    for name in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "AWS_DEFAULT_REGION", "AWS_REGION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))


@pytest.fixture
def fixed_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    """moto has no Pricing API: every price lookup returns $0.10."""
    from cost_waste_finder.pricing import PricingClient

    monkeypatch.setattr(PricingClient, "get_price", lambda self, service, filters: 0.10)
