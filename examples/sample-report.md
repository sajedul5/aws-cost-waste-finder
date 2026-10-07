# AWS cost waste report

Regions (4): ap-south-1, ap-southeast-1, ap-southeast-2, us-east-1 · Scanned: 2026-10-07

**You can save ~$352.19/month** (8 findings)

| Check | Resource ID | Region | Reason | Monthly cost |
|---|---|---|---|---:|
| idle-ec2 | i-0aaa1111bbbb2222c | ap-southeast-2 | m5.xlarge running, avg CPU 1.2%, network 0.3 MB/day (14 days) | $175.20 |
| unattached-ebs | vol-0eee5555ffff6666a | ap-south-1 | Unattached volume (status available), 500 GiB gp2 | $57.00 |
| idle-nat-gateway | nat-0ccc3333dddd4444e | ap-southeast-1 | NAT Gateway sent 0.02 GB in 14 days | $43.07 |
| stopped-ec2 | i-0bbb7777cccc8888d | ap-southeast-1 | t3.xlarge stopped 74 days, still paying for 2 volumes (300 GiB) | $28.80 |
| gp2-to-gp3 | vol-0aaa2222bbbb3333c | ap-southeast-2 | gp2 volume (1000 GiB) can be changed to gp3 with the same IOPS | $24.00 |
| idle-load-balancer | app/old-api/1a2b3c4d5e6f7a8b | us-east-1 | ALB with no registered targets | $16.43 |
| old-snapshot | snap-0ddd9999eeee0000f | ap-south-1 | Snapshot 260 days old, not used by any AMI, up to 80.72 GiB | $4.04 |
| unattached-eip | eipalloc-0f1e2d3c4b5a6978 | ap-southeast-1 | Elastic IP not associated with any instance or network interface | $3.65 |
| **Total** | | | | **$352.19** |
