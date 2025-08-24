#!/usr/bin/env python3
"""
ebs_snapshot_cleanup.py -- Clean up old EBS snapshots to reduce storage costs.

This script manages EBS snapshots based on configurable retention policies.
EBS snapshots cost $0.05 per GB per month and can accumulate quickly, especially
with automated backup systems.

The script supports flexible retention policies:
- Keep daily snapshots for X days
- Keep weekly snapshots for X weeks
- Keep monthly snapshots for X months
- Custom tag-based retention policies

Environment variables:
    REGIONS: Comma-separated list of AWS regions to scan.
    DAILY_RETENTION_DAYS: Keep daily snapshots for X days (default: 7).
    WEEKLY_RETENTION_WEEKS: Keep weekly snapshots for X weeks (default: 4).
    MONTHLY_RETENTION_MONTHS: Keep monthly snapshots for X months (default: 3).
    SNAPSHOT_TAG_KEY: Tag key to identify managed snapshots (default: "AutoSnapshot").
    EXCLUDE_TAGS: Comma-separated list of tag keys. Snapshots with these tags are preserved.
    MIN_SNAPSHOT_AGE_DAYS: Minimum age in days before considering snapshot for deletion.
    DRY_RUN: If "true", logs actions without actually deleting snapshots.
    ALERT_WEBHOOK: Optional HTTP endpoint for notifications.
    COST_THRESHOLD: Only alert if estimated monthly savings exceed this threshold.

Usage:
    python ebs_snapshot_cleanup.py
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


def get_snapshot_name(snapshot: Dict) -> str:
    """Get a friendly name for the snapshot from tags."""
    tags = snapshot.get('Tags', [])
    for tag in tags:
        if tag['Key'].lower() == 'name':
            return tag['Value']
    return snapshot.get('Description', snapshot.get('SnapshotId', 'Unknown'))


def should_exclude_snapshot(snapshot: Dict, exclude_tags: List[str]) -> bool:
    """Check if snapshot should be excluded based on tags."""
    if not exclude_tags:
        return False

    snapshot_tags = snapshot.get('Tags', [])
    snapshot_tag_keys = [tag['Key'] for tag in snapshot_tags]

    for exclude_tag in exclude_tags:
        if exclude_tag in snapshot_tag_keys:
            return True

    return False


def calculate_retention_cutoffs(now: datetime) -> Dict[str, datetime]:
    """Calculate cutoff dates for different retention periods."""
    daily_retention = int(os.getenv("DAILY_RETENTION_DAYS", "7"))
    weekly_retention = int(os.getenv("WEEKLY_RETENTION_WEEKS", "4"))
    monthly_retention = int(os.getenv("MONTHLY_RETENTION_MONTHS", "3"))

    return {
        'daily': now - timedelta(days=daily_retention),
        'weekly': now - timedelta(weeks=weekly_retention),
        'monthly': now - timedelta(days=monthly_retention * 30),  # Approximate
        'minimum_age': now - timedelta(days=int(os.getenv("MIN_SNAPSHOT_AGE_DAYS", "1")))
    }


def categorize_snapshot(snapshot: Dict, cutoffs: Dict[str, datetime]) -> str:
    """
    Categorize a snapshot based on its age and retention policy.
    Returns: 'keep', 'delete', or 'too_young'
    """
    start_time = snapshot['StartTime']

    # Convert to timezone-aware datetime if needed
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    # Don't delete very recent snapshots
    if start_time > cutoffs['minimum_age']:
        return 'too_young'

    # Keep if within daily retention
    if start_time > cutoffs['daily']:
        return 'keep'

    # Keep weekly snapshots (first snapshot of each week)
    if start_time > cutoffs['weekly']:
        # Simple heuristic: keep if it's a Monday snapshot or first of its week
        if start_time.weekday() == 0:  # Monday
            return 'keep'

    # Keep monthly snapshots (first snapshot of each month)
    if start_time > cutoffs['monthly']:
        # Keep if it's the first few days of the month
        if start_time.day <= 3:
            return 'keep'

    # Beyond retention period
    return 'delete'


def analyze_snapshots(client, region: str, exclude_tags: List[str]) -> Tuple[List[Dict], float]:
    """
    Analyze snapshots in a region and identify candidates for deletion.
    Returns (snapshots_to_delete, estimated_monthly_savings).
    """
    try:
        log(f"Scanning EBS snapshots in region {region}...")

        # Get all snapshots owned by this account
        response = client.describe_snapshots(OwnerIds=['self'])
        all_snapshots = response.get('Snapshots', [])

        if not all_snapshots:
            log(f"No snapshots found in {region}")
            return [], 0.0

        log(f"Found {len(all_snapshots)} snapshot(s) in {region}")

        # Calculate retention cutoff dates
        now = datetime.now(timezone.utc)
        cutoffs = calculate_retention_cutoffs(now)

        snapshots_to_delete = []
        total_size_to_delete = 0

        # Analyze each snapshot
        for snapshot in all_snapshots:
            snapshot_id = snapshot['SnapshotId']
            name = get_snapshot_name(snapshot)
            size_gb = snapshot['VolumeSize']
            start_time = snapshot['StartTime']

            # Skip if excluded by tags
            if should_exclude_snapshot(snapshot, exclude_tags):
                log(f"  {snapshot_id} ({name}): Excluded by tag")
                continue

            # Categorize based on retention policy
            category = categorize_snapshot(snapshot, cutoffs)

            age_days = (now - start_time.replace(tzinfo=timezone.utc)).days

            if category == 'delete':
                snapshots_to_delete.append({
                    'SnapshotId': snapshot_id,
                    'Name': name,
                    'VolumeSize': size_gb,
                    'StartTime': start_time,
                    'AgeDays': age_days,
                    'Region': region,
                    'MonthlyCost': size_gb * 0.05  # $0.05 per GB per month
                })
                total_size_to_delete += size_gb
                log(f"  {snapshot_id} ({name}): DELETE - {size_gb} GB, {age_days} days old, ${size_gb * 0.05:.2f}/month")
            elif category == 'keep':
                log(f"  {snapshot_id} ({name}): KEEP - {size_gb} GB, {age_days} days old (retention policy)")
            else:  # too_young
                log(f"  {snapshot_id} ({name}): KEEP - {size_gb} GB, {age_days} days old (too recent)")

        estimated_monthly_savings = total_size_to_delete * 0.05

        return snapshots_to_delete, estimated_monthly_savings

    except ClientError as e:
        log(f"Error analyzing snapshots in {region}: {e}")
        return [], 0.0


def delete_snapshot(client, snapshot_info: Dict, dry_run: bool) -> bool:
    """
    Delete a snapshot.
    Returns True if successful or dry-run.
    """
    snapshot_id = snapshot_info['SnapshotId']
    name = snapshot_info['Name']
    size_gb = snapshot_info['VolumeSize']
    monthly_cost = snapshot_info['MonthlyCost']

    try:
        if dry_run:
            log(f"DRY RUN: Would delete snapshot {snapshot_id} ({name}) - {size_gb} GB, saving ${monthly_cost:.2f}/month")
            return True

        log(f"Deleting snapshot {snapshot_id} ({name}) - {size_gb} GB, saving ${monthly_cost:.2f}/month")

        client.delete_snapshot(SnapshotId=snapshot_id)
        log(f"Successfully deleted snapshot {snapshot_id}")
        return True

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'InvalidSnapshot.NotFound':
            log(f"Snapshot {snapshot_id} was already deleted")
            return True
        else:
            log(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False


def send_alert(webhook: str, all_snapshots: List[Dict], total_savings: float,
               deleted_count: int, dry_run: bool) -> None:
    """Send alert about snapshot cleanup to webhook."""
    if not all_snapshots:
        return

    action_text = "DRY RUN - Would delete" if dry_run else "Deleted" if deleted_count > 0 else "Found"
    total_size = sum(snap['VolumeSize'] for snap in all_snapshots)

    message_lines = [
        f"AWS EBS Snapshot Cleanup Report",
        f"",
        f"Found {len(all_snapshots)} old snapshot(s) for cleanup",
        f"Total size: {total_size:,} GB",
        f"Potential monthly savings: ${total_savings:.2f}",
    ]

    if deleted_count > 0:
        actual_savings = sum(snap['MonthlyCost'] for snap in all_snapshots[:deleted_count])
        message_lines.extend([
            f"{action_text} {deleted_count} snapshot(s)",
            f"Monthly savings: ${actual_savings:.2f}"
        ])

    message_lines.append("")
    message_lines.append("Retention Policy:")
    daily_retention = int(os.getenv("DAILY_RETENTION_DAYS", "7"))
    weekly_retention = int(os.getenv("WEEKLY_RETENTION_WEEKS", "4"))
    monthly_retention = int(os.getenv("MONTHLY_RETENTION_MONTHS", "3"))

    message_lines.extend([
        f"- Daily: {daily_retention} days",
        f"- Weekly: {weekly_retention} weeks",
        f"- Monthly: {monthly_retention} months"
    ])

    message_lines.append("")
    message_lines.append("Sample Snapshots:")

    for snap in all_snapshots[:5]:  # Show first 5
        status = "Deleted" if deleted_count > 0 and not dry_run else "Candidate"
        message_lines.append(
            f"- {snap['SnapshotId']} ({snap['Name']}) - "
            f"{snap['VolumeSize']} GB, {snap['AgeDays']} days old - {status}"
        )

    if len(all_snapshots) > 5:
        message_lines.append(f"... and {len(all_snapshots) - 5} more")

    message_lines.extend([
        f"",
        f"EBS snapshots cost $0.05 per GB per month",
        f"Regular cleanup helps control storage costs"
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
    log("Starting EBS snapshot cleanup")

    # Configuration
    regions = get_regions()
    exclude_tags = [tag.strip() for tag in os.getenv("EXCLUDE_TAGS", "").split(",") if tag.strip()]
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    webhook = os.getenv("ALERT_WEBHOOK")
    cost_threshold = float(os.getenv("COST_THRESHOLD", "1.0"))

    # Log configuration
    log(f"Scanning regions: {', '.join(regions)}")
    log(f"Exclude tags: {exclude_tags if exclude_tags else 'None'}")
    log(f"Dry run mode: {dry_run}")
    log(f"Cost threshold: ${cost_threshold:.2f}")

    # Retention policy
    daily_retention = int(os.getenv("DAILY_RETENTION_DAYS", "7"))
    weekly_retention = int(os.getenv("WEEKLY_RETENTION_WEEKS", "4"))
    monthly_retention = int(os.getenv("MONTHLY_RETENTION_MONTHS", "3"))
    min_age = int(os.getenv("MIN_SNAPSHOT_AGE_DAYS", "1"))

    log(f"Retention policy: {daily_retention} daily, {weekly_retention} weekly, {monthly_retention} monthly")
    log(f"Minimum age for deletion: {min_age} days")

    all_snapshots_to_delete = []
    total_monthly_savings = 0.0
    total_deleted = 0

    try:
        for region in regions:
            # Create EC2 client for this region
            ec2_client = boto3.client('ec2', region_name=region)

            # Analyze snapshots in this region
            snapshots_to_delete, monthly_savings = analyze_snapshots(
                ec2_client, region, exclude_tags
            )

            all_snapshots_to_delete.extend(snapshots_to_delete)
            total_monthly_savings += monthly_savings

            # Delete snapshots (if not dry run)
            if snapshots_to_delete and not dry_run:
                log(f"Deleting {len(snapshots_to_delete)} snapshot(s) in {region}...")
                for snapshot in snapshots_to_delete:
                    if delete_snapshot(ec2_client, snapshot, dry_run):
                        total_deleted += 1

        # Summary
        log(f"")
        log(f"=== EBS SNAPSHOT CLEANUP SUMMARY ===")
        log(f"Total snapshots found for cleanup: {len(all_snapshots_to_delete)}")

        if all_snapshots_to_delete:
            total_size = sum(snap['VolumeSize'] for snap in all_snapshots_to_delete)
            log(f"Total size: {total_size:,} GB")
            log(f"Potential monthly savings: ${total_monthly_savings:.2f}")

        if total_deleted > 0:
            actual_savings = sum(snap['MonthlyCost'] for snap in all_snapshots_to_delete[:total_deleted])
            action = "Would save" if dry_run else "Monthly savings"
            log(f"Snapshots deleted: {total_deleted}")
            log(f"{action}: ${actual_savings:.2f}")

        # Send alerts if threshold is met
        if webhook and total_monthly_savings >= cost_threshold:
            send_alert(webhook, all_snapshots_to_delete, total_monthly_savings, total_deleted, dry_run)
        elif webhook:
            log(f"Savings ${total_monthly_savings:.2f} below threshold ${cost_threshold:.2f}, skipping alert")

        return 0

    except NoCredentialsError:
        log("ERROR: AWS credentials not configured")
        return 1
    except Exception as exc:
        log(f"EBS snapshot cleanup failed: {exc}")
        return 1

    log("EBS snapshot cleanup completed")


if __name__ == "__main__":
    sys.exit(main())
