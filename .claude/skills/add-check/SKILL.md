---
name: add-check
description: How to add a new waste check to cost_waste_finder (check module in checks/, Finding model, registration, moto unit test, docs/checks.md row). Use whenever implementing or changing a check.
---

# Add a waste check

A check is a function that takes a boto3 `Session`, a region and `Thresholds` and returns a list of
`Finding`s. It must be **read-only** (`Describe*`, `List*`, `Get*` only) and never hard-code a region.

## 1. Write the check: `src/cost_waste_finder/checks/<name>.py`
- One module per check, named after what it finds (e.g. `unattached_ebs.py`).
- Signature: `def check(session: boto3.Session, region: str, thresholds: Thresholds) -> list[Finding]:`
  Idle checks that use time also take `now: datetime | None = None` so tests can move time.
- Use paginators for every `Describe*`/`List*` call.
- Thresholds (days, CPU %, etc.) go in `config.Thresholds` with a default and a matching `cwf scan`
  option in `cli.py`. Never magic numbers inline.
- CloudWatch data: use `metrics.daily_values()`; skip resources younger than `lookback_days`.
- Leave `monthly_cost` to the pricing layer unless the check already knows it.

## 2. Return `Finding`s (`src/cost_waste_finder/models.py`)
Fill every field: `check` (short id, e.g. `unattached-ebs`), `resource_id`, `region`,
`reason` (plain English, e.g. "Volume unattached (status available), 100 GiB gp3"),
and the details pricing needs (type, size). Don't put account IDs or ARNs in `reason`.

## 3. Register it
Add the function to the check registry in `src/cost_waste_finder/checks/__init__.py`
so the scanner runs it.

## 4. Test with moto: `tests/checks/test_<name>.py`
- Use `@mock_aws` (or the shared fixture in `tests/conftest.py`) with fake credentials. No real AWS.
- Create both a **wasteful** and a **healthy** resource; assert only the wasteful one is found.
- Cover threshold edges (e.g. 89 vs 91 days) where it matters.
- Use a non-default region (e.g. `ap-southeast-1`) to prove the region is passed through.
- moto can't fake CloudWatch metrics fully: put metric data with `put_metric_data` in the test
  or stub the metric-fetching helper.

## 5. Document it
- Add or update the row in `docs/checks.md`: what it finds, logic, thresholds, IAM permissions.
- New IAM action? It must also go in `iam/read-only-policy.json` (from step 8).
- A notable design choice? One line in `docs/decisions.md`.

## 6. Verify
`.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest`
