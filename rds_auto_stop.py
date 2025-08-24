#!/usr/bin/env python3
"""
rds_auto_stop.py -- Automatically stop RDS instances based on tags.

This script connects to one or more AWS regions and scans for RDS instances
that have a specific tag key/value (e.g. `auto-off=true`). For each matching
instance that is currently available (running), it will attempt to stop the
instance. RDS instances can be expensive, and stopping them during off-hours
can provide significant cost savings.

Note: RDS instances cannot be hibernated like EC2, but stopping them still
saves compute costs while preserving storage and configuration.

Environment variables:
    REGIONS: Comma-separated list of AWS regions to scan. If not set,
        defaults to the region specified in AWS_DEFAULT_REGION or us-east-1.
    TAG_KEY: The tag key to look for (default: "auto-off").
    TAG_VALUE: The tag value to look for (default: "true").
    SKIP_MULTI_AZ: If "true", skip Multi-AZ instances (they may be critical).
    SKIP_READ_REPLICAS: If "true", skip read replica instances.
    SKIP_CLUSTER_INSTANCES: If "true", skip Aurora cluster instances.
    DRY_RUN: If "true", logs actions without actually stopping instances.
    ALERT_WEBHOOK: Optional HTTP endpoint for notifications.

Usage:
    python rds_auto_stop.py
"""

import os
import sys
import json
from datetime import datetime
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


def get_db_instance_name(db_instance: Dict) -> str:
    """Get a friendly name for the DB instance."""
    # Use the DB instance identifier as the name
    return db_instance.get('DBInstanceIdentifier', 'Unknown')


def should_skip_instance(db_instance: Dict, skip_multi_az: bool, skip_read_replicas: bool,
                        skip_cluster_instances: bool) -> Tuple[bool, str]:
    """
    Check if instance should be skipped based on configuration.
    Returns (should_skip, reason).
    """
    # Check if it's a Multi-AZ instance
    if skip_multi_az and db_instance.get('MultiAZ', False):
        return True, "Multi-AZ instance (high availability)"

    # Check if it's a read replica
    if skip_read_replicas and db_instance.get('ReadReplicaSourceDBInstanceIdentifier'):
        return True, "Read replica instance"

    # Check if it's part of a cluster
    if skip_cluster_instances and db_instance.get('DBClusterIdentifier'):
        return True, "Aurora cluster member"

    # Check if it's already stopped or stopping
    db_status = db_instance.get('DBInstanceStatus', '').lower()
    if db_status in ['stopped', 'stopping']:
        return True, f"Already {db_status}"

    # Check if it's not in a stoppable state
    if db_status not in ['available']:
        return True, f"Not available (status: {db_status})"

    return False, ""


def get_db_tags(client, db_instance_arn: str) -> List[Dict]:
    """Get tags for a DB instance."""
    try:
        response = client.list_tags_for_resource(ResourceName=db_instance_arn)
        return response.get('TagList', [])
    except ClientError as e:
        log(f"Failed to get tags for {db_instance_arn}: {e}")
        return []


def has_required_tag(tags: List[Dict], tag_key: str, tag_value: str) -> bool:
    """Check if the required tag is present with the correct value."""
    for tag in tags:
        if tag.get('Key') == tag_key and tag.get('Value') == tag_value:
            return True
    return False


def list_rds_instances(client, tag_key: str, tag_value: str, region: str) -> List[Dict]:
    """Return a list of RDS instances that match the tag criteria and are stoppable."""
    instances = []

    try:
        # Get all DB instances
        paginator = client.get_paginator("describe_db_instances")

        for page in paginator.paginate():
            for db_instance in page.get("DBInstances", []):
                db_instance_id = db_instance['DBInstanceIdentifier']
                db_instance_arn = db_instance['DBInstanceArn']

                # Get tags for this instance
                tags = get_db_tags(client, db_instance_arn)

                # Check if it has the required tag
                if has_required_tag(tags, tag_key, tag_value):
                    instances.append({
                        **db_instance,
                        'Tags': tags,
                        'Region': region
                    })

    except ClientError as e:
        log(f"Error listing RDS instances in {region}: {e}")

    return instances


def stop_rds_instance(client, db_instance_id: str, dry_run: bool) -> bool:
    """
    Attempt to stop an RDS instance.
    Returns True if the request was submitted successfully.
    """
    try:
        if dry_run:
            log(f"DRY RUN: Would stop RDS instance {db_instance_id}")
            return True

        log(f"Stopping RDS instance {db_instance_id}...")

        # Note: RDS doesn't have a DryRun parameter like EC2
        response = client.stop_db_instance(
            DBInstanceIdentifier=db_instance_id,
            # Optionally create a snapshot before stopping
            # DBSnapshotIdentifier=f"{db_instance_id}-auto-stop-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        )

        log(f"Stop request submitted for RDS instance {db_instance_id}")
        return True

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'InvalidDBInstanceState':
            log(f"RDS instance {db_instance_id} is not in a state where it can be stopped: {e}")
        else:
            log(f"Error stopping RDS instance {db_instance_id}: {e}")
        return False


def estimate_monthly_savings(db_instances: List[Dict]) -> float:
    """
    Estimate monthly savings from stopping RDS instances.
    This is a rough estimate based on typical pricing.
    """
    savings = 0.0

    # Rough estimates for compute savings (storage costs continue)
    # These are approximate and vary by region
    instance_costs = {
        'db.t3.micro': 14.6,    # $0.020/hour
        'db.t3.small': 29.2,    # $0.040/hour
        'db.t3.medium': 58.4,   # $0.080/hour
        'db.t3.large': 116.8,   # $0.160/hour
        'db.t3.xlarge': 233.6,  # $0.320/hour
        'db.m5.large': 131.4,   # $0.180/hour
        'db.m5.xlarge': 262.8,  # $0.360/hour
        'db.r5.large': 182.5,   # $0.250/hour
        'db.r5.xlarge': 365.0,  # $0.500/hour
    }

    for instance in db_instances:
        instance_class = instance.get('DBInstanceClass', '')
        monthly_cost = instance_costs.get(instance_class, 50.0)  # Default estimate
        savings += monthly_cost

    return savings


def send_alert(webhook: str, summary: List[Dict], estimated_savings: float) -> None:
    """Send a summary message to the given webhook URL."""
    if not summary:
        return

    lines = [
        "RDS Auto-Stop Summary:",
        f"",
        f"Estimated monthly savings: ${estimated_savings:.2f}",
        f"",
    ]

    for entry in summary:
        lines.append(
            f"- {entry['region']} - {entry['db_instance_id']} ({entry['instance_class']}) "
            f"- {entry['action']} ({entry['state']})"
        )

    lines.extend([
        f"",
        f"Note: Storage costs continue while instances are stopped",
        f"Restart instances when needed with AWS console or CLI"
    ])

    payload = {"text": "\n".join(lines)}

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
    log("Starting RDS auto-stop script")

    # Configuration
    tag_key = os.getenv("TAG_KEY", "auto-off")
    tag_value = os.getenv("TAG_VALUE", "true")
    skip_multi_az = os.getenv("SKIP_MULTI_AZ", "false").lower() == "true"
    skip_read_replicas = os.getenv("SKIP_READ_REPLICAS", "false").lower() == "true"
    skip_cluster_instances = os.getenv("SKIP_CLUSTER_INSTANCES", "false").lower() == "true"
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    webhook = os.getenv("ALERT_WEBHOOK")

    regions = get_regions()
    summary: List[Dict] = []

    log(f"Scanning regions: {', '.join(regions)}")
    log(f"Looking for tag: {tag_key}={tag_value}")
    log(f"Skip Multi-AZ: {skip_multi_az}")
    log(f"Skip Read Replicas: {skip_read_replicas}")
    log(f"Skip Cluster Instances: {skip_cluster_instances}")
    log(f"Dry run mode: {dry_run}")

    try:
        for region in regions:
            log(f"Scanning region {region} for RDS instances tagged {tag_key}={tag_value}...")

            # Create RDS client for this region
            rds_client = boto3.client("rds", region_name=region)

            # Find matching instances
            instances = list_rds_instances(rds_client, tag_key, tag_value, region)
            log(f"Found {len(instances)} matching RDS instance(s) in {region}")

            for instance in instances:
                db_instance_id = instance["DBInstanceIdentifier"]
                instance_class = instance.get("DBInstanceClass", "Unknown")
                engine = instance.get("Engine", "Unknown")

                # Check if we should skip this instance
                should_skip, reason = should_skip_instance(
                    instance, skip_multi_az, skip_read_replicas, skip_cluster_instances
                )

                if should_skip:
                    log(f"Skipping {db_instance_id} ({instance_class}): {reason}")
                    summary.append({
                        "region": region,
                        "db_instance_id": db_instance_id,
                        "instance_class": instance_class,
                        "engine": engine,
                        "action": "skipped",
                        "state": reason,
                    })
                    continue

                log(f"Stopping RDS instance {db_instance_id} ({instance_class}, {engine}) in {region}...")
                success = stop_rds_instance(rds_client, db_instance_id, dry_run)
                state = "requested" if success else "failed"

                summary.append({
                    "region": region,
                    "db_instance_id": db_instance_id,
                    "instance_class": instance_class,
                    "engine": engine,
                    "action": "stopping",
                    "state": state,
                })

        # Calculate estimated savings
        stopped_instances = [s for s in summary if s['action'] == 'stopping' and s['state'] == 'requested']
        estimated_savings = estimate_monthly_savings([
            {'DBInstanceClass': s['instance_class']} for s in stopped_instances
        ])

        # Send webhook notification
        if webhook and summary:
            send_alert(webhook, summary, estimated_savings)

        # Final summary
        total_found = len([s for s in summary if s['action'] != 'skipped'])
        total_stopped = len(stopped_instances)
        total_skipped = len([s for s in summary if s['action'] == 'skipped'])

        log(f"")
        log(f"=== RDS AUTO-STOP SUMMARY ===")
        log(f"Total instances found: {total_found}")
        log(f"Total instances stopped: {total_stopped}")
        log(f"Total instances skipped: {total_skipped}")

        if estimated_savings > 0:
            action = "Estimated monthly savings" if not dry_run else "Potential monthly savings"
            log(f"{action}: ${estimated_savings:.2f}")

        log("RDS auto-stop script completed")
        return 0

    except NoCredentialsError:
        log("ERROR: AWS credentials not configured")
        return 1
    except Exception as exc:
        log(f"RDS auto-stop script failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
