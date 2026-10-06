# Decisions

Short log of design decisions. Newest at the bottom.

| # | Decision | Why |
|---|---|---|
| 1 | Local CLI only, no Lambda | Simple to run against client accounts without deploying anything into them. |
| 2 | No Cost Explorer in `cwf scan` (see #22) | It charges per API call; the Pricing API and resource metadata are free. |
| 3 | Read-only API calls only (`Describe*`, `List*`, `Get*`, Pricing) | Safe to run in client accounts; matches a minimal read-only IAM policy. |
| 4 | Default credential chain, no stored keys; `--role-arn` for client accounts | No secrets in the repo or config; works with SSO, profiles and assumed roles. |
| 5 | No hard-coded region | `--region`, else the AWS config default. Clients use different regions. |
| 6 | Pricing API in `us-east-1`, filtered by location name | The Pricing API is only served from a few regions; prices are per location. |
| 7 | moto for all tests; CI never calls real AWS | Fast, free, deterministic, and no credentials in CI. |
| 8 | Owner does all git commits, pushes and PRs | Enforced via `.claude/settings.json` deny rules. |
| 9 | Optional local `.env` (gitignored), loaded by `cwf` without overriding the shell | Convenience for local runs. Prefer `AWS_PROFILE`/SSO; if keys, only a read-only IAM user. Claude is denied reading `.env`. |
| 10 | hatchling build, src/ layout, CI on Python 3.11 and 3.13 | Simple packaging; src/ layout makes tests use the installed package. Covers the minimum and a current Python. |
| 11 | Region → Pricing location name from botocore's bundled endpoint data | No extra API call, no hand-maintained table; covers every region botocore knows. |
| 12 | EBS cost = storage GB-month only (no extra IOPS/throughput yet) | Simple first version; errs on the side of under-estimating savings. |
| 13 | Pricing tests use botocore `Stubber`, not moto | moto doesn't implement the Pricing API; Stubber is offline too. |
| 14 | A failing check or pricing call warns and continues | One missing IAM permission shouldn't hide every other finding. |
| 15 | Report goes to stdout only (no files) until `--output` in step 9 | Avoids writing real account data to disk by accident. |
| 16 | Snapshot cost uses full snapshot size: shown as "up to" | AWS doesn't expose the billed incremental size via Describe calls; an upper bound is honest. |
| 17 | gp2→gp3 saving subtracts gp3 IOPS needed to match gp2 baseline; only in-use volumes | Avoids overstating savings on large volumes and double counting unattached volumes. |
| 18 | `get_price` matches a usagetype without its region prefix (exact, see #21) | Usagetypes start with a region code (`APS1-...`), so exact TERM_MATCH filters can't select them. |
| 19 | Thresholds live in one `Thresholds` dataclass and every value is a CLI option | One place for defaults; easy to tune per client. |
| 20 | Idle checks need a full lookback of history: NAT/LB by creation time, EC2 by CloudWatch data points (≥ lookback − 1 days) | Not enough history to call them idle. EC2 `LaunchTime` resets on every stop/start, so a rebooted idle server would be missed. |
| 21 | Usagetype match is exact after a `[A-Z0-9]+-` prefix, not "ends with" | "Ends with LoadBalancerUsage" also matched Trust Store and Outposts products. |
| 22 | Cost Explorer allowed only in `cwf bill` / `cwf dashboard` (steps 10–11), opt-in | Owner wants a 3-month bill trend; free CloudWatch billing metrics were empty in their account. ~$0.01 per call, call count printed. |
| 23 | Stopped time comes from `StateTransitionReason`; unreadable = skipped | It's the only Describe field with the stop time; guessing would give wrong ages. |
| 24 | `--all-regions` scans only enabled regions, sequentially, with one shared price cache | Opt-in regions that aren't enabled would fail; sequential keeps the code simple (17 regions ≈ 2 min). |
