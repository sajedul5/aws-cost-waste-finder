# Checks

Every check is read-only. Status shows which plan step adds it. Thresholds will be configurable
where noted. Keep this table current (see the `add-check` skill).

| Check | Finds | Logic | Thresholds | IAM permissions | Status |
|---|---|---|---|---|---|
| `unattached-ebs` | EBS volumes not attached to any instance | `DescribeVolumes` with `status=available` | none | `ec2:DescribeVolumes` | done (step 2) |
| `old-snapshot` | Old EBS snapshots no AMI uses | Own snapshots older than N days whose ID isn't in any own AMI's block device mappings. Cost = full size (or volume size) × snapshot GB-month (archive tier priced separately): an upper bound, since snapshots are incremental | `min_age_days=90` | `ec2:DescribeSnapshots`, `ec2:DescribeImages` | done (step 5) |
| `unattached-eip` | Elastic IPs not associated | `DescribeAddresses` with no `AssociationId`. Cost = idle public IPv4 hourly price × 730 | none | `ec2:DescribeAddresses` | done (step 5) |
| `gp2-to-gp3` | Attached gp2 volumes that could be gp3 (~20% cheaper) | `DescribeVolumes` with `volume-type=gp2`, `status=in-use` (unattached ones are `unattached-ebs`). Saving = size × (gp2 − gp3) − gp3 IOPS needed to match gp2 baseline (3/GiB, max 16,000; 3,000 free). Throughput ignored | none | `ec2:DescribeVolumes` | done (step 5) |
| `idle-ec2` | Running instances doing almost nothing | Avg CPU and network over N days below thresholds | 14 days, CPU <5%, low network | `ec2:DescribeInstances`, `cloudwatch:GetMetricStatistics` | planned (step 6) |
| `idle-nat-gateway` | NAT Gateways with near-zero traffic | `BytesOutToDestination` sum over N days below threshold | 14 days | `ec2:DescribeNatGateways`, `cloudwatch:GetMetricStatistics` | planned (step 6) |
| `idle-load-balancer` | ALB/NLB/CLB with no targets or near-zero requests | No registered/healthy targets, or request count below threshold | 14 days | `elasticloadbalancing:Describe*`, `cloudwatch:GetMetricStatistics` | planned (step 6) |
| `stopped-ec2` | Instances stopped a long time that still pay for volumes | State `stopped`, transition time older than N days, has EBS volumes | 30 days | `ec2:DescribeInstances`, `ec2:DescribeVolumes` | planned (step 7) |

Pricing for all checks uses `pricing:GetProducts` (called in `us-east-1`), on-demand USD.
EBS costs are storage GB-month only; extra provisioned IOPS/throughput (io1/io2, gp3 above baseline) are not included yet.
