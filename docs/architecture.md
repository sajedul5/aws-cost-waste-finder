# Architecture

```
cwf scan  ──►  scanner  ──►  checks/*  ──►  pricing  ──►  report
 (CLI)        (session,      (read-only     (Pricing API,   (sorted table,
              regions)        Describe*)     cached)         total savings)
```

## Components (`src/cost_waste_finder/`)

| Component | Responsibility |
|---|---|
| `cli.py` | Commands `scan` and `web`. Shared `ROLE_OPTIONS` and `@threshold_options`; `open_session()`, `run_scan()` and `emit()` keep commands short. |
| `session.py` | `make_session()`: default credential chain, or `sts:AssumeRole` into a client's read-only role (`--role-arn`, optional `--external-id`, 1 hour). All clients use adaptive retries (throttling). |
| `scanner.py` | `scan(session, region)` runs every check in `CHECKS`, then prices the findings. `scan_regions()` loops over regions; `enabled_regions()` lists the account's enabled regions. A check that fails with an API or network error (AccessDenied, unreachable endpoint, timeout) is skipped with a warning on stderr; credential errors stop the scan. `remove_overlaps()` drops findings already counted by another check (gp2 volumes on a stopped instance) before pricing; a pricing failure leaves costs as n/a. |
| `checks/` | One module per waste check. Each takes `(session, region, thresholds)` and returns `list[Finding]`. Read-only calls only. Registered in `checks/__init__.py`. |
| `config.py` | `Thresholds` dataclass: lookback days and per-check limits; every value is a `cwf scan` option. |
| `metrics.py` | `daily_values()`: one CloudWatch `GetMetricStatistics` value per day (Average or Sum) for the idle checks. |
| `models.py` | `Finding` dataclass: check id, resource ID, region, reason, details, monthly cost. |
| `pricing.py` | `PricingClient`: Pricing API `GetProducts` in `us-east-1`, filtered by the scanned region's location name (e.g. "Asia Pacific (Singapore)", from botocore's region data), on-demand USD price (follows `NextToken`), in-memory cache per run with one lock per lookup. Lookups: EBS storage, gp3 IOPS, snapshot storage (standard/archive), idle public IPv4 (AmazonVPC), EC2 instance (OS + SQL Server from `PlatformDetails`), NAT Gateway, load balancer (AWSELB). Products can be picked by usagetype without its region prefix. `apply_costs()` fills `monthly_cost` (the monthly saving) via a check-id → cost-function map; unknown prices stay `None`. |
| `report.py` | `report_reason()` adds "verify before deleting" to heuristic findings (idle LB, old snapshot) in every format. `render_markdown()`: region(s) + date header (no account ID), "You can save ~$X/month", table sorted by monthly cost (unpriced last, shown n/a), total row. `render_csv()` (data rows only, formula-injection safe) and `render_json()` (with `details`). |
| `html_report.py` | `render_html()`: one self-contained page, inline CSS (light/dark), all text escaped, no scripts, nothing loaded from the web (only link: the optional "Prepared by" LinkedIn/email). `page()` (which can take a script, used only by `cwf web`) and `report_body()` are reused by the web page. |
| `branding.py` | Optional "Prepared by" details (name, title, email, LinkedIn) from `CWF_*` environment variables, so they stay in the user's own `.env`, not the public repo. |
| `pdf_report.py` | `render_pdf()`: client PDF with fpdf2 (pure Python): title "<Company> - AWS Cost Waste Report", AWS-console-like navy bar with orange line, title and scan time, a blue "Prepared by" note (clickable email and "LinkedIn" links, URL not shown), "Summary" box and plain findings table, savings per month and year, findings table, total, page footer. Built-in fonts, so non-Latin characters become `?`. |
| `web.py` | `cwf web`: standard-library HTTP server. `/` page "AWS Cost Waste Audit" with the branding card, company name + Scan, and the latest report; `POST /scan` scans all enabled regions (one at a time); `/report.pdf` download. Only localhost host names are accepted and cross-site posts are refused. |
| `output.py` | `RENDERERS` for `--format markdown|csv|json|html`; `write_report()` for `--output FILE`. |

## Data flow

1. CLI resolves the regions: `--region`, else the AWS config default (never hard-coded), or with
   `--all-regions` every region enabled for the account (`DescribeRegions`).
2. Scanner uses one `boto3.Session` and one `PricingClient` (shared, locked price cache);
   `scan_regions()` scans up to 8 regions in parallel threads (progress on stderr) and calls each
   check per region. Findings keep the region order.
3. Each check paginates `Describe*`/`List*` calls (and CloudWatch `GetMetricStatistics` for
   idle checks) and returns findings without cost.
4. Pricing fills `monthly_cost` per finding, caching prices by (service, region, attributes).
5. The chosen renderer sorts by savings and prints to stdout, or writes `--output FILE`.

Packaging: `pipx install` from Git (entry point `cwf`), or the `Dockerfile` (non-root, credentials
mounted at run time; `.dockerignore` keeps `.env`, `reports/` and tests out of the image). The image
installs pinned, hash-checked dependencies from `requirements.lock`. After changing dependencies in
`pyproject.toml`, refresh it:

```sh
docker run --rm -v "$PWD:/out" -w /out python:3.13-slim sh -c "pip install -q pip-tools && \
  pip-compile -q --generate-hashes --strip-extras --no-header -o requirements.lock pyproject.toml"
```

## Boundaries

- Runs locally only; credentials come from the user's environment, or an assumed client role.
- Minimum IAM permissions: `iam/read-only-policy.json` (see `docs/iam.md`); a test checks it covers every call.
- No writes to AWS, no Cost Explorer, no data leaves the machine except AWS API calls.
- Tests use moto; CI never has AWS credentials.
