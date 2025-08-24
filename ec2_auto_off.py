#!/usr/bin/env python3
"""
ec2_auto_off.py -- Automatically stop or hibernate EC2 instances based on a tag.

This script connects to one or more AWS regions and scans for EC2 instances
that have a specific tag key/value (e.g. `auto-off=true`). For each matching
instance that is currently running, it will attempt to stop the instance. If
hibernate mode is enabled (via an environment variable or flag), the script
passes the `Hibernate=True` parameter to the EC2 stop API. According to
AWS documentation and guidance from the Cloud Custodian project, specifying
`Hibernate=True` will cause EC2 to attempt to hibernate the instance if it
is configured for hibernation; if not, the instance will fall back to a
normal stop【371153541882818†L4653-L4674】.

Hibernating an instance saves the contents of the instance's memory to its
EBS root volume and persists all attached volumes. AWS notes that during
hibernation you are only charged for the storage of the EBS volumes (including
the saved memory dump) and that there are no compute or data‑transfer charges
during the hibernated period【544552484446559†L48-L60】. To successfully
hibernate, the instance must be launched with hibernation enabled, the root
volume must be an encrypted EBS volume, and the root volume must have enough
space to store the RAM contents; otherwise hibernation will fail and the
instance will simply stop【453126371038636†L350-L363】.

Configuration is done via environment variables to make this script easy to
deploy in CI/CD systems such as GitHub Actions. See the docstring at the
top of the script for available variables.

Environment variables:
    REGIONS: Comma-separated list of AWS regions to scan. If not set,
        defaults to the region specified in AWS_DEFAULT_REGION or
        us-east-1.
    TAG_KEY: The tag key to look for (default: "auto-off").
    TAG_VALUE: The tag value to look for (default: "true").
    HIBERNATE: If set to "true", attempt to hibernate instances instead
        of stopping them. Hibernation requires that the instances be
        configured for hibernation. If hibernation fails, the instance
        will fall back to a normal stop【371153541882818†L4653-L4674】.
    DRY_RUN: If set to "true", the script will log the actions it would
        take without actually calling the stop API.
    ALERT_WEBHOOK: Optional HTTP endpoint (e.g. Slack/Discord) to send
        a summary of actions taken.

Usage:
    python ec2_auto_off.py
"""

import os
import sys
import json
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
import requests


def log(msg: str) -> None:
    """Prints a timestamped message to stdout."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}")


def get_regions() -> list[str]:
    regions_env = os.getenv("REGIONS")
    if regions_env:
        return [r.strip() for r in regions_env.split(",") if r.strip()]
    default = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    return [default]


def list_instances(client, tag_key: str, tag_value: str) -> list[dict]:
    """Return a list of running instance IDs that match the tag criteria."""
    filters = [
        {"Name": "instance-state-name", "Values": ["running"]},
        {"Name": f"tag:{tag_key}", "Values": [tag_value]},
    ]
    instances = []
    paginator = client.get_paginator("describe_instances")
    for page in paginator.paginate(Filters=filters):
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instances.append(instance)
    return instances


def stop_instance(client, instance_id: str, hibernate: bool, dry_run: bool) -> bool:
    """Attempt to stop or hibernate an instance.

    Returns True if the request was submitted successfully.
    """
    try:
        kwargs = {"InstanceIds": [instance_id]}
        if hibernate:
            # Request hibernation; unsupported instances will just stop【371153541882818†L4653-L4674】.
            kwargs["Hibernate"] = True
        if dry_run:
            kwargs["DryRun"] = True
        response = client.stop_instances(**kwargs)
        return True
    except ClientError as e:
        if e.response["Error"].get("Code") == "DryRunOperation":
            # DryRunOperation indicates the call would have succeeded without DryRun.
            return True
        log(f"Error stopping instance {instance_id}: {e}")
        return False


def send_alert(webhook: str, summary: list[dict]) -> None:
    """Send a summary message to the given webhook URL."""
    lines = ["EC2 auto-off summary:"]
    for entry in summary:
        lines.append(
            f"- {entry['region']} {entry['instance_id']}: {entry['action']} "
            f"({entry['state']})"
        )
    payload = {"text": "\n".join(lines)}
    try:
        requests.post(webhook, json=payload, timeout=10)
    except Exception as exc:
        log(f"Failed to send alert: {exc}")


def main() -> int:
    tag_key = os.getenv("TAG_KEY", "auto-off")
    tag_value = os.getenv("TAG_VALUE", "true")
    hibernate = os.getenv("HIBERNATE", "false").lower() == "true"
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    webhook = os.getenv("ALERT_WEBHOOK")

    regions = get_regions()
    summary: list[dict] = []

    for region in regions:
        log(f"Scanning region {region} for instances tagged {tag_key}={tag_value}...")
        client = boto3.client("ec2", region_name=region)
        instances = list_instances(client, tag_key, tag_value)
        log(f"Found {len(instances)} matching running instance(s) in {region}")
        for instance in instances:
            instance_id = instance["InstanceId"]
            if hibernate:
                action = "hibernating"
            else:
                action = "stopping"
            log(f"{action.capitalize()} instance {instance_id} in {region}...")
            success = stop_instance(client, instance_id, hibernate, dry_run)
            state = "requested" if success else "failed"
            summary.append(
                {
                    "region": region,
                    "instance_id": instance_id,
                    "action": action,
                    "state": state,
                }
            )

    if webhook and summary:
        send_alert(webhook, summary)

    log("Finished EC2 auto-off script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())