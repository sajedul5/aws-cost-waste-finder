# Checks

Every check is read-only. Status shows which plan step adds it. Thresholds are `cwf scan` options
(defaults in `config.py`). Keep this table current (see the `add-check` skill).

| Check | Finds | Logic | Thresholds | IAM permissions | Status |
|---|---|---|---|---|---|
| `unattached-ebs` | EBS volumes not attached to any instance | `DescribeVolumes` with `status=available` | none | `ec2:DescribeVolumes` | done (step 2) |
| `old-snapshot` | Old EBS snapshots no AMI uses | Own snapshots older than N days whose ID isn't in any own AMI's block device mappings. Cost = full size (or volume size) × snapshot GB-month (archive tier priced separately): an upper bound, since snapshots are incremental | `--snapshot-age-days 90` | `ec2:DescribeSnapshots`, `ec2:DescribeImages` | done (step 5) |
| `unattached-eip` | Elastic IPs not associated | `DescribeAddresses` with no `AssociationId`. Cost = idle public IPv4 hourly price × 730 | none | `ec2:DescribeAddresses` | done (step 5) |
| `gp2-to-gp3` | Attached gp2 volumes that could be gp3 (~20% cheaper) | `DescribeVolumes` with `volume-type=gp2`, `status=in-use` (unattached ones are `unattached-ebs`). Saving = size × (gp2 − gp3) − gp3 IOPS needed to match gp2 baseline (3/GiB, max 16,000; 3,000 free). Throughput ignored | none | `ec2:DescribeVolumes` | done (step 5) |
| `idle-ec2` | Running instances doing almost nothing | Running instances with at least lookback − 1 days of CloudWatch data (not `LaunchTime`, which resets on stop/start); daily `CPUUtilization` average and `NetworkIn`+`NetworkOut` sum. Idle if avg CPU and MB/day are both below thresholds; no data = skipped. Saving = on-demand hourly price (Linux or Windows) × 730, compute only | `--lookback-days 14`, `--cpu-threshold 5`, `--network-threshold-mb 5` | `ec2:DescribeInstances`, `cloudwatch:GetMetricStatistics` | done (step 6) |
| `idle-nat-gateway` | NAT Gateways with near-zero traffic | Available NAT Gateways older than the lookback; `BytesOutToDestination` + `BytesOutToSource` sum below threshold. Saving = hourly price × 730 (data processing not counted) | `--lookback-days 14`, `--nat-threshold-gb 1` | `ec2:DescribeNatGateways`, `cloudwatch:GetMetricStatistics` | done (step 6) |
| `idle-load-balancer` | ALB/NLB/Classic ELB with no targets or near-zero traffic | Older than the lookback; no registered targets (ALB/NLB: target groups + target health; Classic: instances), or `RequestCount` (ALB, Classic) / `NewFlowCount` (NLB) sum below threshold. Gateway LBs skipped. Saving = hourly price × 730 (LCU not counted). Report ID is `app/name/id`, not the ARN | `--lookback-days 14`, `--lb-requests-threshold 100` | `elasticloadbalancing:DescribeLoadBalancers`, `elasticloadbalancing:DescribeTargetGroups`, `elasticloadbalancing:DescribeTargetHealth`, `cloudwatch:GetMetricStatistics` | done (step 6) |
| `stopped-ec2` | Instances stopped a long time that still pay for their EBS volumes | Stopped instances; stop time parsed from `StateTransitionReason` ("User initiated (… GMT)"), skipped if it can't be read. Reported when stopped longer than threshold and has EBS volumes (`DescribeVolumes` for size/type). Saving = storage of those volumes (no compute is billed while stopped) | `--stopped-days 30` | `ec2:DescribeInstances`, `ec2:DescribeVolumes` | done (step 7) |

All permissions together: `iam/read-only-policy.json` (plus `ec2:DescribeRegions` for `--all-regions`).
Pricing for all checks uses `pricing:GetProducts` (called in `us-east-1`), on-demand USD.
Idle checks skip resources without a full lookback of history (EC2: CloudWatch data; NAT/LB: creation time).
EBS costs are storage GB-month only; extra provisioned IOPS/throughput (io1/io2, gp3 above baseline) are not included yet.
