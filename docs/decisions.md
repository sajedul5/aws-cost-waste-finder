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
| 24 | `--all-regions` scans only enabled regions, 8 in parallel (threads), with one shared, locked price cache | Opt-in regions that aren't enabled would fail. The work is waiting on AWS: 17 regions went from 2 min 10 s to 20 s. boto3 Sessions aren't thread-safe, so only client creation is locked (`ThreadSafeSession`). |
| 25 | Client access via `sts:AssumeRole` into a read-only role, with an optional external ID | No shared keys; the client controls and can delete the role; external ID prevents confused-deputy misuse. |
| 26 | A test records every AWS call in a full moto scan and checks it against the IAM policy | The policy can't silently fall behind the code; also asserts the policy is Describe/Get/List only. |
| 27 | HTML report is one self-contained file: inline CSS, no JavaScript, no external links | Safe to email or attach for a client; works offline; nothing to load or track. |
| 28 | CSV cells starting with `= + - @` get a leading `'` | Prevents formula injection when a client opens the CSV in Excel/Sheets (resource names come from their account). |
| 29 | Docker image runs as non-root; credentials are mounted, never built in | `.dockerignore` excludes `.env`, `reports/`, `.git`; CI builds the image on every PR. |
| 30 | Bill trend: 2 full months + current month so far with AWS forecast; per-service current month uses a simple projection | Fair comparison (a half month always looks lower). One forecast call for the total keeps the cost at ~2 calls (~$0.02); a forecast per service would cost one call each. |
| 31 | Cost Explorer permissions are a separate `CwfBillOptional` statement | A client can allow the waste scan without sharing bill data. |
| 32 | Dashboard scans all enabled regions by default and includes the bill unless `--no-bill` | It's the whole-account view for decisions; `--no-bill` keeps it free. |
| 33 | Dashboard charts are inline SVG / CSS bars generated in Python, no chart library | One file that works offline and is safe to email; no CDN or JavaScript. |
| 34 | Waste audit only: `cwf bill` and `cwf dashboard` removed (supersedes #22, #30–#33) | It's a free, public open-source tool: no Cost Explorer charges, smaller scope. The owner keeps bill analysis for paid client work. |
| 35 | `cwf web` uses the standard-library `http.server`, local only | No web framework to install or maintain; listens on 127.0.0.1 (Docker: publish to 127.0.0.1 only); Host and Origin checks block DNS rebinding and cross-site posts. |
| 36 | PDF with fpdf2 instead of a headless browser or WeasyPrint | Pure Python, real one-click download. Adds ~75 MB to the image (Pillow, fonttools) vs ~150 MB+ for WeasyPrint system libraries or a browser. Built-in fonts: Latin-1 only. |
| 37 | "Prepared by" contact details come from `CWF_*` env vars, not code | Public tool: each user's reports show their own details; the owner's contact info isn't published in the repo. Only `https://` LinkedIn links are accepted. |
