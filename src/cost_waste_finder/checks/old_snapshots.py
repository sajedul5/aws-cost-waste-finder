"""Check: own EBS snapshots older than N days that no own AMI uses."""

from datetime import UTC, datetime, timedelta

import boto3

from cost_waste_finder.config import Thresholds
from cost_waste_finder.models import Finding

CHECK_ID = "old-snapshot"
BYTES_PER_GIB = 1024**3
# Markers AWS Backup and Data Lifecycle Manager put on their snapshots. "aws:" tags can only be
# set by AWS itself, so they can't be faked by a user tag.
MANAGED_TAG_PREFIXES = ("aws:backup:", "aws:dlm:")
MANAGED_DESCRIPTIONS = (
    "This snapshot is created by the AWS Backup service",
    "Created for policy: ",
)


def check(
    session: boto3.Session,
    region: str,
    thresholds: Thresholds,
    now: datetime | None = None,
) -> list[Finding]:
    ec2 = session.client("ec2", region_name=region)
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=thresholds.snapshot_age_days)
    used_by_ami = _snapshots_used_by_own_amis(ec2)

    findings = []
    for page in ec2.get_paginator("describe_snapshots").paginate(OwnerIds=["self"]):
        for snapshot in page["Snapshots"]:
            if snapshot["StartTime"] >= cutoff or snapshot["SnapshotId"] in used_by_ami:
                continue
            if is_retention_managed(snapshot):
                continue  # kept on purpose by AWS Backup or Data Lifecycle Manager
            age_days = (now - snapshot["StartTime"]).days
            # Snapshots are incremental: the full size is an upper bound of what is billed.
            full_bytes = snapshot.get("FullSnapshotSizeInBytes")
            size_gib = (
                round(full_bytes / BYTES_PER_GIB, 2) if full_bytes else snapshot["VolumeSize"]
            )
            archive = snapshot.get("StorageTier") == "archive"
            findings.append(
                Finding(
                    check=CHECK_ID,
                    resource_id=snapshot["SnapshotId"],
                    region=region,
                    reason=(
                        f"Snapshot {age_days} days old, not used by any AMI, up to {size_gib} GiB"
                        + (" (archive tier)" if archive else "")
                    ),
                    details={"size_gib": size_gib, "age_days": age_days, "archive": archive},
                )
            )
    return findings


def is_retention_managed(snapshot: dict) -> bool:
    """Owned by a backup/retention policy, which deletes it on schedule: not waste."""
    if any(tag["Key"].startswith(MANAGED_TAG_PREFIXES) for tag in snapshot.get("Tags", [])):
        return True
    return snapshot.get("Description", "").startswith(MANAGED_DESCRIPTIONS)


def _snapshots_used_by_own_amis(ec2) -> set[str]:
    used = set()
    # Disabled AMIs are hidden by default but still need their snapshots to be re-enabled.
    pages = ec2.get_paginator("describe_images").paginate(Owners=["self"], IncludeDisabled=True)
    for page in pages:
        for image in page["Images"]:
            for mapping in image.get("BlockDeviceMappings", []):
                snapshot_id = mapping.get("Ebs", {}).get("SnapshotId")
                if snapshot_id:
                    used.add(snapshot_id)
    return used
