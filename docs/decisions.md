# Decisions

Short log of design decisions. Newest at the bottom.

| # | Decision | Why |
|---|---|---|
| 1 | Local CLI only, no Lambda | Simple to run against client accounts without deploying anything into them. |
| 2 | No Cost Explorer | It charges per API call; the Pricing API and resource metadata are free. |
| 3 | Read-only API calls only (`Describe*`, `List*`, `Get*`, Pricing) | Safe to run in client accounts; matches a minimal read-only IAM policy. |
| 4 | Default credential chain, no stored keys; `--role-arn` for client accounts | No secrets in the repo or config; works with SSO, profiles and assumed roles. |
| 5 | No hard-coded region | `--region`, else the AWS config default. Clients use different regions. |
| 6 | Pricing API in `us-east-1`, filtered by location name | The Pricing API is only served from a few regions; prices are per location. |
| 7 | moto for all tests; CI never calls real AWS | Fast, free, deterministic, and no credentials in CI. |
| 8 | Owner does all git commits, pushes and PRs | Enforced via `.claude/settings.json` deny rules. |
| 9 | Optional local `.env` (gitignored), loaded by `cwf` without overriding the shell | Convenience for local runs. Prefer `AWS_PROFILE`/SSO; if keys, only a read-only IAM user. Claude is denied reading `.env`. |
| 10 | hatchling build, src/ layout, CI on Python 3.11 and 3.13 | Simple packaging; src/ layout makes tests use the installed package. Covers the minimum and a current Python. |
