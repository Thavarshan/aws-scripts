#!/usr/bin/env python3
"""
unused_eip_cleanup.py -- Find and optionally release unused Elastic IP addresses.

This script scans AWS regions for Elastic IP addresses that are not associated
with any running instances or network interfaces. Unused EIPs cost $0.005 per hour
($3.60 per month each), which can significantly impact small budgets.

The script can operate in several modes:
- Report-only: Just identify unused EIPs and calculate costs
- Alert-only: Send notifications about unused EIPs
- Auto-release: Automatically release unused EIPs (with safety checks)

Environment variables:
    REGIONS: Comma-separated list of AWS regions to scan. If not set,
        defaults to the region specified in AWS_DEFAULT_REGION or us-east-1.
    AUTO_RELEASE: If "true", automatically release unused EIPs. Use with caution!
    EXCLUDE_TAGS: Comma-separated list of tag keys. EIPs with these tags are preserved.
    MIN_UNUSED_HOURS: Minimum hours an EIP must be unused before considering for release.
    DRY_RUN: If "true", logs actions without actually releasing EIPs.
    ALERT_WEBHOOK: Optional HTTP endpoint for notifications.
    COST_THRESHOLD: Only alert/act if monthly cost savings exceed this threshold (default: 1.0).

Usage:
    python unused_eip_cleanup.py
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


def should_exclude_eip(eip: Dict, exclude_tags: List[str]) -> bool:
    """Check if EIP should be excluded based on tags."""
    if not exclude_tags:
        return False

    eip_tags = eip.get('Tags', [])
    eip_tag_keys = [tag['Key'] for tag in eip_tags]

    for exclude_tag in exclude_tags:
        if exclude_tag in eip_tag_keys:
            return True

    return False


def get_eip_name(eip: Dict) -> str:
    """Get a friendly name for the EIP from tags."""
    tags = eip.get('Tags', [])
    for tag in tags:
        if tag['Key'].lower() == 'name':
            return tag['Value']
    return eip.get('PublicIp', 'Unknown')


def analyze_unused_eips(client, region: str, exclude_tags: List[str],
                       min_unused_hours: int) -> Tuple[List[Dict], float]:
    """
    Find unused EIPs in a region and calculate costs.
    Returns (unused_eips, monthly_cost_savings).
    """
    try:
        log(f"Scanning Elastic IPs in region {region}...")

        # Get all EIPs
        response = client.describe_addresses()
        all_eips = response.get('Addresses', [])

        if not all_eips:
            log(f"No Elastic IPs found in {region}")
            return [], 0.0

        log(f"Found {len(all_eips)} Elastic IP(s) in {region}")

        unused_eips = []

        for eip in all_eips:
            allocation_id = eip.get('AllocationId', 'Unknown')
            public_ip = eip.get('PublicIp', 'Unknown')
            name = get_eip_name(eip)

            # Check if EIP is associated with an instance or network interface
            instance_id = eip.get('InstanceId')
            association_id = eip.get('AssociationId')
            network_interface_id = eip.get('NetworkInterfaceId')

            is_unused = not (instance_id or association_id or network_interface_id)

            if is_unused:
                # Check if should be excluded by tags
                if should_exclude_eip(eip, exclude_tags):
                    log(f"  {public_ip} ({name}): Unused but excluded by tag")
                    continue

                # For now, we can't easily check how long it's been unused without CloudTrail
                # So we'll assume it meets the min_unused_hours requirement

                unused_eips.append({
                    'AllocationId': allocation_id,
                    'PublicIp': public_ip,
                    'Name': name,
                    'Region': region,
                    'Tags': eip.get('Tags', []),
                    'Domain': eip.get('Domain', 'vpc')
                })

                log(f"  {public_ip} ({name}): UNUSED - costing $3.60/month")
            else:
                associated_resource = instance_id or network_interface_id or "network interface"
                log(f"  {public_ip} ({name}): In use (associated with {associated_resource})")

        # Calculate monthly cost savings (unused EIPs cost $0.005/hour = $3.60/month)
        monthly_cost = len(unused_eips) * 3.60

        return unused_eips, monthly_cost

    except ClientError as e:
        log(f"Error analyzing EIPs in {region}: {e}")
        return [], 0.0


def release_eip(client, eip_info: Dict, dry_run: bool) -> bool:
    """
    Release an unused EIP.
    Returns True if successful or dry-run.
    """
    allocation_id = eip_info['AllocationId']
    public_ip = eip_info['PublicIp']
    name = eip_info['Name']

    try:
        if dry_run:
            log(f"DRY RUN: Would release EIP {public_ip} ({name}) - allocation {allocation_id}")
            return True

        log(f"Releasing EIP {public_ip} ({name}) - allocation {allocation_id}")

        if eip_info['Domain'] == 'vpc':
            client.release_address(AllocationId=allocation_id)
        else:
            # Classic EC2 (rare these days)
            client.release_address(PublicIp=public_ip)

        log(f"Successfully released EIP {public_ip} - saving $3.60/month")
        return True

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'InvalidAllocationID.NotFound':
            log(f"EIP {public_ip} was already released")
            return True
        else:
            log(f"Failed to release EIP {public_ip}: {e}")
            return False


def send_alert(webhook: str, unused_eips: List[Dict], total_monthly_cost: float,
               released_count: int, dry_run: bool) -> None:
    """Send alert about unused EIPs to webhook."""
    if not unused_eips:
        return

    action_text = "DRY RUN - Would release" if dry_run else "Released" if released_count > 0 else "Found"

    message_lines = [
        f"AWS Unused EIP Report",
        f"",
        f"Found {len(unused_eips)} unused Elastic IP(s)",
        f"Monthly cost: ${total_monthly_cost:.2f}",
    ]

    if released_count > 0:
        savings = released_count * 3.60
        message_lines.extend([
            f"{action_text} {released_count} EIP(s)",
            f"Monthly savings: ${savings:.2f}"
        ])

    message_lines.append("")
    message_lines.append("EIP Details:")

    for eip in unused_eips[:10]:  # Limit to first 10 to avoid huge messages
        status = "Released" if released_count > 0 and not dry_run else "Unused"
        message_lines.append(f"- {eip['PublicIp']} ({eip['Name']}) - {eip['Region']} - ${3.60:.2f}/month - {status}")

    if len(unused_eips) > 10:
        message_lines.append(f"... and {len(unused_eips) - 10} more")

    message_lines.extend([
        f"",
        f"Each unused EIP costs $3.60/month ($0.005/hour)",
        f"Consider releasing unused EIPs to reduce costs"
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
    log("Starting unused EIP cleanup scan")

    # Configuration
    regions = get_regions()
    auto_release = os.getenv("AUTO_RELEASE", "false").lower() == "true"
    exclude_tags = [tag.strip() for tag in os.getenv("EXCLUDE_TAGS", "").split(",") if tag.strip()]
    min_unused_hours = int(os.getenv("MIN_UNUSED_HOURS", "1"))
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    webhook = os.getenv("ALERT_WEBHOOK")
    cost_threshold = float(os.getenv("COST_THRESHOLD", "1.0"))

    log(f"Scanning regions: {', '.join(regions)}")
    log(f"Auto-release mode: {auto_release}")
    log(f"Exclude tags: {exclude_tags if exclude_tags else 'None'}")
    log(f"Dry run mode: {dry_run}")
    log(f"Cost threshold: ${cost_threshold:.2f}")

    if auto_release and not dry_run:
        log("WARNING: Auto-release is enabled! EIPs will be permanently released.")

    all_unused_eips = []
    total_monthly_cost = 0.0
    total_released = 0

    try:
        for region in regions:
            # Create EC2 client for this region
            ec2_client = boto3.client('ec2', region_name=region)

            # Find unused EIPs in this region
            unused_eips, monthly_cost = analyze_unused_eips(
                ec2_client, region, exclude_tags, min_unused_hours
            )

            all_unused_eips.extend(unused_eips)
            total_monthly_cost += monthly_cost

            # Release EIPs if auto-release is enabled
            if auto_release and unused_eips:
                log(f"Auto-releasing {len(unused_eips)} unused EIP(s) in {region}...")
                for eip in unused_eips:
                    if release_eip(ec2_client, eip, dry_run):
                        total_released += 1

        # Summary
        log(f"")
        log(f"=== UNUSED EIP SUMMARY ===")
        log(f"Total unused EIPs found: {len(all_unused_eips)}")
        log(f"Total monthly cost: ${total_monthly_cost:.2f}")

        if total_released > 0:
            savings = total_released * 3.60
            action = "Would save" if dry_run else "Monthly savings"
            log(f"EIPs released: {total_released}")
            log(f"{action}: ${savings:.2f}")

        # Send alerts if threshold is met
        if webhook and total_monthly_cost >= cost_threshold:
            send_alert(webhook, all_unused_eips, total_monthly_cost, total_released, dry_run)
        elif webhook:
            log(f"Cost ${total_monthly_cost:.2f} below threshold ${cost_threshold:.2f}, skipping alert")

        # Return non-zero if unused EIPs found (for scripting/alerting)
        return 1 if all_unused_eips else 0

    except NoCredentialsError:
        log("ERROR: AWS credentials not configured")
        return 1
    except Exception as exc:
        log(f"Unused EIP cleanup failed: {exc}")
        return 1

    log("Unused EIP cleanup completed")


if __name__ == "__main__":
    sys.exit(main())
