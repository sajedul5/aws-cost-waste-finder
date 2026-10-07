# aws-cost-waste-finder

`cwf` is a read-only Python CLI that scans an AWS account for wasted spend (unattached EBS,
old snapshots, idle EC2/NAT/LBs, unused Elastic IPs, ...) and prints a report like
"You can save ~$X/month", listing each finding with resource ID, region, reason and monthly
cost. It runs locally only. Public portfolio project for AWS cost-optimization freelancing.

Details: @docs/architecture.md @docs/checks.md @docs/decisions.md

## Rules (always follow)
- Read-only: only `Describe*`, `List*`, `Get*` calls, the Pricing API and `sts:AssumeRole` (for `--role-arn`). Never create, modify or delete AWS resources.
- No Cost Explorer (charged per call): this is a free tool.
- No Lambda: local CLI only. Never scan real AWS from CI.
- No stored keys in the repo: default AWS credential chain (optional gitignored `.env`, see `.env.example`), or `--role-arn` for client accounts (docs/iam.md). Never read `.env`.
- Never hard-code a region: `--region`, else the AWS config default. (Owner's account: ap-southeast-1.)
- Never commit account IDs, ARNs, real reports or client data. Use fake IDs in examples.
- Every check gets a moto unit test. Every AWS call must be in `iam/read-only-policy.json` (enforced by `tests/test_iam_policy.py`). CI never calls real AWS.
- No LICENSE file.
- Simple, readable code. Python 3.11+, type hints, ruff (lint + format), pytest, local `.venv`.

## Git rules
- Allowed: `git switch`, `git pull`, `git switch -c`, `git status`, `git diff`, `git log`.
- Never: `git add`, `git commit`, `git push`, `git merge`, `gh pr create`, `gh pr merge`. The owner does these.

## Plan
- [x] 0. Claude Code setup: CLAUDE.md, .claude/settings.json, skills, docs/
- [x] 1. Setup: src/ package `cost_waste_finder`, pyproject.toml, minimal `cwf` CLI, GitHub Actions CI (ruff + pytest)
- [x] 2. Check: unattached EBS volumes
- [x] 3. Pricing API client (us-east-1, location filter, in-memory cache); findings get monthly cost
- [x] 4. Report + CLI: `cwf scan [--region]`, Markdown table sorted by savings, plus total
- [x] 5. Checks: old snapshots (>90d, not used by AMI), unattached EIPs, gp2 -> gp3
- [x] 6. CloudWatch checks (14d, configurable thresholds): idle EC2, idle NAT GW, idle LBs
- [x] 7. Stopped EC2 >30d with volumes; `--all-regions`
- [x] 8. `--role-arn` and iam/read-only-policy.json
- [x] 9. `--format markdown|csv|json|html`, `--output FILE`, pipx install, Dockerfile
- [x] 10. `cwf bill` (Cost Explorer): removed again in step 11
- [x] 11. Waste audit only: remove `cwf bill` and `cwf dashboard`; no Cost Explorer
- [ ] 12. `cwf web`: local page (organization name + Scan), waste report, Download PDF; Docker
- [ ] 13. README polish, examples/sample-report.md (fake IDs), architecture diagram

## Commands
```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # setup
.venv/bin/ruff check . && .venv/bin/ruff format --check .     # lint
.venv/bin/pytest                                               # test
.venv/bin/cwf scan --region ap-southeast-1                     # run (real AWS: owner approves)
.venv/bin/cwf scan --all-regions --format html --output reports/scan.html   # file report
pipx install git+https://github.com/sajedul5/aws-cost-waste-finder           # install
docker build -t cwf . && docker run --rm -v ~/.aws:/home/cwf/.aws:ro -e AWS_PROFILE cwf scan
```

## How to work on each step
1. `git switch main && git pull`, then `git switch -c step-N-short-name`.
2. Give the owner a short bullet plan for the step and wait for OK before writing code.
3. Write code + tests (new checks: use the `add-check` skill). Keep CLAUDE.md and docs/ current.
4. Run the `step-handoff` skill. From step 4 on, include the `cwf scan --region ap-southeast-1` command.
5. STOP. Don't start the next step until the owner says "next".

Context habits: keep this file short (details go in docs/ and skills), read only the files the
current step needs, and ask only when a decision is really the owner's.
