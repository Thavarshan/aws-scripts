#!/usr/bin/env python3
"""
unused_ebs_detector.py -- Find unattached EBS volumes that are costing money.

This script scans AWS regions for EBS volumes that are not attached to any EC2
instances. Unattached volumes continue to incur storage costs based on their size
and type. The script can identify these volumes, calculate their costs, and
optionally create snapshots before deletion.

EBS Volume Pricing (approximate):
- gp3: $0.08 per GB per month
- gp2: $0.10 per GB per month
- io1: $0.125 per GB per month + IOPS costs
- st1: $0.045 per GB per month
- sc1: $0.025 per GB per month

Environment variables:
    REGIONS: Comma-separated list of AWS regions to scan.
    MIN_UNUSED_HOURS: Minimum hours a volume must be unattached (default: 24).
    EXCLUDE_TAGS: Comma-separated list of tag keys. Volumes with these tags are preserved.
    CREATE_SNAPSHOTS: If "true", create snapshots before suggesting deletion.
    AUTO_DELETE: If "true", automatically delete unused volumes (USE WITH EXTREME CAUTION).
    DRY_RUN: If "true", logs actions without making changes.
    ALERT_WEBHOOK: Optional HTTP endpoint for notifications.
    COST_THRESHOLD: Only alert if monthly cost exceeds this threshold.

Usage:
    python unused_ebs_detector.py
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import requests


def log(msg: str) -> None:
    """Prints a timestamped message to stdout."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}")


def get_regions() -> List[str]:
    """Get list of regions to scan."""
    regions_env = os.getenv("REGIONS")
    if regions_env:
        return [r.strip() for r in regions_env.split(",") if r.strip()]
    default = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    return [default]


def get_volume_name(volume: Dict) -> str:
    """Get a friendly name for the volume from tags."""
    tags = volume.get('Tags', [])
    for tag in tags:
        if tag['Key'].lower() == 'name':
            return tag['Value']
    return f"vol-{volume['VolumeId'][-8:]}"


def should_exclude_volume(volume: Dict, exclude_tags: List[str]) -> bool:
    """Check if volume should be excluded based on tags."""
    if not exclude_tags:
        return False

    volume_tags = volume.get('Tags', [])
    volume_tag_keys = [tag['Key'] for tag in volume_tags]

    for exclude_tag in exclude_tags:
        if exclude_tag in exclude_tag_keys:
            return True

    return False


def calculate_monthly_cost(volume: Dict) -> float:
    """Calculate monthly cost for a volume based on its type and size."""
    volume_type = volume['VolumeType']
    size_gb = volume['Size']
    iops = volume.get('Iops', 0)

    # Base storage costs per GB per month (approximate)
    storage_costs = {
        'gp3': 0.08,
        'gp2': 0.10,
        'io1': 0.125,
        'io2': 0.125,
        'st1': 0.045,
        'sc1': 0.025,
        'standard': 0.05  # Legacy magnetic volumes
    }

    base_cost = size_gb * storage_costs.get(volume_type, 0.10)

    # Add IOPS costs for provisioned IOPS volumes
    if volume_type in ['io1', 'io2'] and iops > 0:
        # io1/io2 IOPS cost approximately $0.065 per IOPS per month
        iops_cost = iops * 0.065
        base_cost += iops_cost

    return base_cost


def get_volume_attachment_time(volume: Dict) -> Optional[datetime]:
    """Get the last time the volume was detached (approximate)."""
    # This is a simplified approach. In reality, you'd need CloudTrail for exact detachment time.
    # We'll use the volume creation time as a fallback
    create_time = volume.get('CreateTime')
    if create_time:
        return create_time.replace(tzinfo=timezone.utc)
    return None


def analyze_unused_volumes(client, region: str, exclude_tags: List[str],
                          min_unused_hours: int) -> Tuple[List[Dict], float]:
    """
    Find unused (unattached) EBS volumes in a region.
    Returns (unused_volumes, total_monthly_cost).
    """
    try:
        log(f"Scanning EBS volumes in region {region}...")

        # Get all volumes
        paginator = client.get_paginator('describe_volumes')
        unused_volumes = []

        for page in paginator.paginate():
            for volume in page['Volumes']:
                volume_id = volume['VolumeId']
                name = get_volume_name(volume)
                state = volume['State']
                size_gb = volume['Size']
                volume_type = volume['VolumeType']

                # Only consider available (unattached) volumes
                if state != 'available':
                    log(f"  {volume_id} ({name}): {state} - {size_gb} GB {volume_type}")
                    continue

                # Check if should be excluded by tags
                if should_exclude_volume(volume, exclude_tags):
                    log(f"  {volume_id} ({name}): Unused but excluded by tag")
                    continue

                # Check minimum unused time (simplified - would need CloudTrail for precision)
                attachment_time = get_volume_attachment_time(volume)
                if attachment_time:
                    hours_unused = (datetime.now(timezone.utc) - attachment_time).total_seconds() / 3600
                    if hours_unused < min_unused_hours:
                        log(f"  {volume_id} ({name}): Unused for only {hours_unused:.1f} hours, keeping")
                        continue

                monthly_cost = calculate_monthly_cost(volume)

                unused_volumes.append({
                    'VolumeId': volume_id,
                    'Name': name,
                    'Size': size_gb,
                    'VolumeType': volume_type,
                    'State': state,
                    'CreateTime': volume.get('CreateTime'),
                    'Region': region,
                    'MonthlyCost': monthly_cost,
                    'Tags': volume.get('Tags', []),
                    'Iops': volume.get('Iops', 0),
                    'AvailabilityZone': volume['AvailabilityZone']
                })

                log(f"  {volume_id} ({name}): UNUSED - {size_gb} GB {volume_type}, ${monthly_cost:.2f}/month")

        total_monthly_cost = sum(vol['MonthlyCost'] for vol in unused_volumes)
        log(f"Found {len(unused_volumes)} unused volume(s) in {region}, total cost: ${total_monthly_cost:.2f}/month")

        return unused_volumes, total_monthly_cost

    except ClientError as e:
        log(f"Error analyzing volumes in {region}: {e}")
        return [], 0.0


def create_snapshot_for_volume(client, volume_info: Dict, dry_run: bool) -> Optional[str]:
    """
    Create a snapshot for a volume before deletion.
    Returns snapshot ID if successful.
    """
    volume_id = volume_info['VolumeId']
    name = volume_info['Name']

    try:
        if dry_run:
            log(f"DRY RUN: Would create snapshot for volume {volume_id} ({name})")
            return f"snap-dryrun-{volume_id[-8:]}"

        log(f"Creating snapshot for volume {volume_id} ({name}) before deletion...")

        description = f"Backup snapshot of {volume_id} ({name}) created before automated deletion"

        response = client.create_snapshot(
            VolumeId=volume_id,
            Description=description,
            TagSpecifications=[
                {
                    'ResourceType': 'snapshot',
                    'Tags': [
                        {'Key': 'Name', 'Value': f"Backup-{name}"},
                        {'Key': 'OriginalVolumeId', 'Value': volume_id},
                        {'Key': 'CreatedBy', 'Value': 'unused-ebs-detector'},
                        {'Key': 'AutoCreated', 'Value': 'true'}
                    ]
                }
            ]
        )

        snapshot_id = response['SnapshotId']
        log(f"Created snapshot {snapshot_id} for volume {volume_id}")
        return snapshot_id

    except ClientError as e:
        log(f"Failed to create snapshot for volume {volume_id}: {e}")
        return None


def delete_volume(client, volume_info: Dict, dry_run: bool) -> bool:
    """
    Delete an unused EBS volume.
    Returns True if successful.
    """
    volume_id = volume_info['VolumeId']
    name = volume_info['Name']
    monthly_cost = volume_info['MonthlyCost']

    try:
        if dry_run:
            log(f"DRY RUN: Would delete volume {volume_id} ({name}) - saving ${monthly_cost:.2f}/month")
            return True

        log(f"Deleting volume {volume_id} ({name}) - saving ${monthly_cost:.2f}/month")

        client.delete_volume(VolumeId=volume_id)
        log(f"Successfully deleted volume {volume_id}")
        return True

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'InvalidVolume.NotFound':
            log(f"Volume {volume_id} was already deleted")
            return True
        else:
            log(f"Failed to delete volume {volume_id}: {e}")
            return False


def send_alert(webhook: str, unused_volumes: List[Dict], total_cost: float,
               action_summary: Dict, dry_run: bool) -> None:
    """Send alert about unused volumes to webhook."""
    if not unused_volumes:
        return

    total_size = sum(vol['Size'] for vol in unused_volumes)
    snapshots_created = action_summary.get('snapshots_created', 0)
    volumes_deleted = action_summary.get('volumes_deleted', 0)

    message_lines = [
        f"AWS Unused EBS Volume Report",
        f"",
        f"Found {len(unused_volumes)} unused volume(s)",
        f"Total monthly cost: ${total_cost:.2f}",
        f"Total size: {total_size:,} GB",
    ]

    if snapshots_created > 0:
        message_lines.append(f"Snapshots created: {snapshots_created}")

    if volumes_deleted > 0:
        action = "Would delete" if dry_run else "Deleted"
        savings = sum(vol['MonthlyCost'] for vol in unused_volumes[:volumes_deleted])
        message_lines.extend([
            f"{action} {volumes_deleted} volume(s)",
            f"Monthly savings: ${savings:.2f}"
        ])

    message_lines.append("")
    message_lines.append("Volume Details:")

    for vol in unused_volumes[:8]:  # Show first 8 volumes
        az = vol.get('AvailabilityZone', 'Unknown')
        status = "Deleted" if volumes_deleted > 0 and not dry_run else "Unused"
        message_lines.append(
            f"- {vol['VolumeId']} ({vol['Name']}) - "
            f"{vol['Size']} GB {vol['VolumeType']} in {az} - "
            f"${vol['MonthlyCost']:.2f}/month - {status}"
        )

    if len(unused_volumes) > 8:
        message_lines.append(f"... and {len(unused_volumes) - 8} more")

    message_lines.extend([
        f"",
        f"Unused EBS volumes continue to incur storage costs",
        f"Consider creating snapshots before deletion for backup",
        f"Regular cleanup helps control storage expenses"
    ])

    payload = {"text": "\n".join(message_lines)}

    try:
        response = requests.post(webhook, json=payload, timeout=10)
        if response.status_code == 200:
            log(f"Alert sent successfully to webhook")
        else:
            log(f"Failed to send alert: HTTP {response.status_code}")
    except Exception as exc:
        log(f"Failed to send alert: {exc}")


def main() -> int:
    """Main function."""
    log("Starting unused EBS volume detection")

    # Configuration
    regions = get_regions()
    min_unused_hours = int(os.getenv("MIN_UNUSED_HOURS", "24"))
    exclude_tags = [tag.strip() for tag in os.getenv("EXCLUDE_TAGS", "").split(",") if tag.strip()]
    create_snapshots = os.getenv("CREATE_SNAPSHOTS", "false").lower() == "true"
    auto_delete = os.getenv("AUTO_DELETE", "false").lower() == "true"
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    webhook = os.getenv("ALERT_WEBHOOK")
    cost_threshold = float(os.getenv("COST_THRESHOLD", "1.0"))

    log(f"Scanning regions: {', '.join(regions)}")
    log(f"Minimum unused hours: {min_unused_hours}")
    log(f"Exclude tags: {exclude_tags if exclude_tags else 'None'}")
    log(f"Create snapshots: {create_snapshots}")
    log(f"Auto-delete mode: {auto_delete}")
    log(f"Dry run mode: {dry_run}")
    log(f"Cost threshold: ${cost_threshold:.2f}")

    if auto_delete and not dry_run:
        log("WARNING: Auto-delete is enabled! Volumes will be permanently deleted.")

    all_unused_volumes = []
    total_monthly_cost = 0.0
    action_summary = {'snapshots_created': 0, 'volumes_deleted': 0}

    try:
        for region in regions:
            # Create EC2 client for this region
            ec2_client = boto3.client('ec2', region_name=region)

            # Find unused volumes
            unused_volumes, monthly_cost = analyze_unused_volumes(
                ec2_client, region, exclude_tags, min_unused_hours
            )

            all_unused_volumes.extend(unused_volumes)
            total_monthly_cost += monthly_cost

            # Create snapshots if requested
            if create_snapshots and unused_volumes:
                log(f"Creating snapshots for {len(unused_volumes)} volume(s) in {region}...")
                for volume in unused_volumes:
                    snapshot_id = create_snapshot_for_volume(ec2_client, volume, dry_run)
                    if snapshot_id:
                        action_summary['snapshots_created'] += 1

            # Delete volumes if auto-delete is enabled
            if auto_delete and unused_volumes:
                log(f"Auto-deleting {len(unused_volumes)} unused volume(s) in {region}...")
                for volume in unused_volumes:
                    if delete_volume(ec2_client, volume, dry_run):
                        action_summary['volumes_deleted'] += 1

        # Summary
        log(f"")
        log(f"=== UNUSED EBS VOLUME SUMMARY ===")
        log(f"Total unused volumes found: {len(all_unused_volumes)}")
        log(f"Total monthly cost: ${total_monthly_cost:.2f}")

        if all_unused_volumes:
            total_size = sum(vol['Size'] for vol in all_unused_volumes)
            log(f"Total size: {total_size:,} GB")

            # Volume type breakdown
            volume_types = {}
            for vol in all_unused_volumes:
                vol_type = vol['VolumeType']
                volume_types[vol_type] = volume_types.get(vol_type, 0) + 1

            log("Volume types:")
            for vol_type, count in volume_types.items():
                log(f"  {vol_type}: {count} volume(s)")

        if action_summary['snapshots_created'] > 0:
            log(f"Snapshots created: {action_summary['snapshots_created']}")

        if action_summary['volumes_deleted'] > 0:
            deleted_cost = sum(vol['MonthlyCost'] for vol in all_unused_volumes[:action_summary['volumes_deleted']])
            action = "Would save" if dry_run else "Monthly savings"
            log(f"Volumes deleted: {action_summary['volumes_deleted']}")
            log(f"{action}: ${deleted_cost:.2f}")

        # Send alerts if threshold is met
        if webhook and total_monthly_cost >= cost_threshold:
            send_alert(webhook, all_unused_volumes, total_monthly_cost, action_summary, dry_run)
        elif webhook:
            log(f"Cost ${total_monthly_cost:.2f} below threshold ${cost_threshold:.2f}, skipping alert")

        return 0

    except NoCredentialsError:
        log("ERROR: AWS credentials not configured")
        return 1
    except Exception as exc:
        log(f"Unused EBS volume detection failed: {exc}")
        return 1

    log("Unused EBS volume detection completed")


if __name__ == "__main__":
    sys.exit(main())
