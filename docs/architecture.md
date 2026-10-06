# Architecture

```
cwf scan  ──►  scanner  ──►  checks/*  ──►  pricing  ──►  report
 (CLI)        (session,      (read-only     (Pricing API,   (sorted table,
              regions)        Describe*)     cached)         total savings)
```

## Components (`src/cost_waste_finder/`)

| Component | Responsibility |
|---|---|
| `cli.py` | Click entry point `cwf`. Parses `--region`, later `--all-regions`, `--role-arn`, `--format`, `--output`. |
| `scanner.py` | Builds the boto3 session (default credential chain, or assumed role), resolves regions, runs every registered check, collects findings. |
| `checks/` | One module per waste check. Each takes `(session, region)` and returns `list[Finding]`. Read-only calls only. Registered in `checks/__init__.py`. |
| `models.py` | `Finding` dataclass: check id, resource ID, region, reason, details, monthly cost. |
| `pricing.py` | `PricingClient`: Pricing API `GetProducts` in `us-east-1`, filtered by the scanned region's location name (e.g. "Asia Pacific (Singapore)", from botocore's region data), on-demand USD price, in-memory cache per run. `apply_costs()` fills `monthly_cost` via a check-id → cost-function map; unknown prices stay `None`. |
| `report.py` | Sorts findings by monthly cost, renders Markdown (later CSV/JSON/HTML), prints "You can save ~$X/month". |

## Data flow

1. CLI resolves the region: `--region`, else the AWS config default. Never hard-coded.
2. Scanner creates one `boto3.Session` and, per region, calls each check.
3. Each check paginates `Describe*`/`List*` calls (and CloudWatch `GetMetricStatistics` for
   idle checks) and returns findings without cost.
4. Pricing fills `monthly_cost` per finding, caching prices by (service, region, attributes).
5. Report sorts by savings, prints the table and the total.

## Boundaries

- Runs locally only; credentials come from the user's environment.
- No writes to AWS, no Cost Explorer, no data leaves the machine except AWS API calls.
- Tests use moto; CI never has AWS credentials.
