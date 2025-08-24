#!/usr/bin/env python3
"""
cloudwatch_logs_optimizer.py -- Manage CloudWatch log retention to control costs.

This script manages CloudWatch log groups to optimize storage costs by:
1. Setting appropriate retention periods on log groups
2. Identifying log groups with no retention policy (infinite retention)
3. Finding unused or old log groups that can be deleted
4. Calculating potential cost savings

CloudWatch Logs pricing (approximate):
- Storage: $0.50 per GB ingested
- Storage: $0.03 per GB per month for retention
- No charges after log expiration

Environment variables:
    REGIONS: Comma-separated list of AWS regions to scan.
    DEFAULT_RETENTION_DAYS: Default retention to apply (default: 14).
    CRITICAL_LOG_RETENTION: Retention for critical logs like Lambda (default: 30).
    SET_RETENTION_POLICIES: If "true", automatically set retention policies.
    DELETE_EMPTY_GROUPS: If "true", delete log groups with no recent activity.
    EMPTY_GROUP_DAYS: Days of inactivity before considering group empty (default: 30).
    EXCLUDE_PATTERNS: Comma-separated patterns of log groups to exclude.
    DRY_RUN: If "true", logs actions without making changes.
    ALERT_WEBHOOK: Optional HTTP endpoint for notifications.

Usage:
    python cloudwatch_logs_optimizer.py
"""

import os
import sys
import json
import re
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


def should_exclude_log_group(log_group_name: str, exclude_patterns: List[str]) -> bool:
    """Check if log group should be excluded based on patterns."""
    for pattern in exclude_patterns:
        if re.search(pattern, log_group_name):
            return True
    return False


def determine_appropriate_retention(log_group_name: str) -> int:
    """Determine appropriate retention period based on log group name."""
    default_retention = int(os.getenv("DEFAULT_RETENTION_DAYS", "14"))
    critical_retention = int(os.getenv("CRITICAL_LOG_RETENTION", "30"))

    # Patterns that suggest longer retention needs
    critical_patterns = [
        r'/aws/lambda/',     # Lambda functions
        r'/aws/apigateway/', # API Gateway
        r'/aws/rds/',        # RDS logs
        r'production',       # Production environments
        r'prod',
        r'security',         # Security-related logs
        r'audit',
        r'error',            # Error logs
    ]

    # Patterns that can have shorter retention
    debug_patterns = [
        r'debug',
        r'development',
        r'dev',
        r'test',
        r'staging',
    ]

    log_group_lower = log_group_name.lower()

    # Check for critical patterns first
    for pattern in critical_patterns:
        if re.search(pattern, log_group_lower):
            return critical_retention

    # Check for debug/dev patterns - can use shorter retention
    for pattern in debug_patterns:
        if re.search(pattern, log_group_lower):
            return max(7, default_retention // 2)  # Minimum 7 days, or half default

    return default_retention


def analyze_log_groups(logs_client, region: str, exclude_patterns: List[str],
                      empty_group_days: int) -> Tuple[List[Dict], float]:
    """
    Analyze CloudWatch log groups in a region.
    Returns (optimization_opportunities, estimated_monthly_savings).
    """
    try:
        log(f"Analyzing CloudWatch log groups in region {region}...")

        opportunities = []
        total_savings = 0.0

        # Get all log groups
        paginator = logs_client.get_paginator('describe_log_groups')

        for page in paginator.paginate():
            for log_group in page['logGroups']:
                log_group_name = log_group['logGroupName']

                # Skip excluded patterns
                if should_exclude_log_group(log_group_name, exclude_patterns):
                    log(f"  Skipping excluded log group: {log_group_name}")
                    continue

                current_retention = log_group.get('retentionInDays')
                stored_bytes = log_group.get('storedBytes', 0)
                stored_gb = stored_bytes / (1024**3)
                creation_time = log_group.get('creationTime', 0)

                # Estimate current monthly cost (rough estimate)
                if current_retention:
                    # With retention, cost is based on stored data
                    current_cost = stored_gb * 0.03  # $0.03 per GB per month
                else:
                    # Without retention, data accumulates indefinitely
                    # Estimate based on age and assume some growth
                    age_months = (datetime.now().timestamp() * 1000 - creation_time) / (1000 * 60 * 60 * 24 * 30)
                    estimated_growth = max(1, age_months * 0.1)  # Rough growth estimate
                    current_cost = stored_gb * 0.03 * estimated_growth

                opportunity = {
                    'log_group_name': log_group_name,
                    'region': region,
                    'current_retention': current_retention,
                    'stored_gb': stored_gb,
                    'current_monthly_cost': current_cost,
                    'creation_time': creation_time,
                    'last_event_time': log_group.get('lastEventTime'),
                }

                # Check if log group needs retention policy
                if not current_retention:
                    appropriate_retention = determine_appropriate_retention(log_group_name)
                    opportunity.update({
                        'issue_type': 'no_retention',
                        'suggested_retention': appropriate_retention,
                        'priority': 'HIGH',
                        'description': f"No retention policy (infinite retention)"
                    })
                    opportunities.append(opportunity)

                # Check if retention is too long
                elif current_retention > 365:  # More than 1 year
                    appropriate_retention = determine_appropriate_retention(log_group_name)
                    if appropriate_retention < current_retention:
                        potential_savings = current_cost * 0.3  # Rough estimate
                        total_savings += potential_savings
                        opportunity.update({
                            'issue_type': 'excessive_retention',
                            'suggested_retention': appropriate_retention,
                            'priority': 'MEDIUM',
                            'description': f"Retention too long: {current_retention} days",
                            'potential_savings': potential_savings
                        })
                        opportunities.append(opportunity)

                # Check if log group appears inactive
                last_event_time = log_group.get('lastEventTime')
                if last_event_time:
                    days_since_last_event = (datetime.now().timestamp() * 1000 - last_event_time) / (1000 * 60 * 60 * 24)
                    if days_since_last_event > empty_group_days:
                        opportunity.update({
                            'issue_type': 'inactive_group',
                            'suggested_action': 'delete',
                            'priority': 'LOW',
                            'description': f"No activity for {int(days_since_last_event)} days",
                            'days_inactive': int(days_since_last_event),
                            'potential_savings': current_cost
                        })
                        opportunities.append(opportunity)
                        total_savings += current_cost
                else:
                    # No last event time might mean very old or empty group
                    age_days = (datetime.now().timestamp() * 1000 - creation_time) / (1000 * 60 * 60 * 24)
                    if age_days > empty_group_days and stored_gb < 0.01:  # Less than 10MB
                        opportunity.update({
                            'issue_type': 'empty_group',
                            'suggested_action': 'delete',
                            'priority': 'LOW',
                            'description': f"Empty group, {int(age_days)} days old",
                            'potential_savings': current_cost
                        })
                        opportunities.append(opportunity)
                        total_savings += current_cost

        return opportunities, total_savings

    except ClientError as e:
        log(f"Error analyzing log groups in {region}: {e}")
        return [], 0.0


def set_log_retention(logs_client, log_group_name: str, retention_days: int, dry_run: bool) -> bool:
    """Set retention policy for a log group."""
    try:
        if dry_run:
            log(f"DRY RUN: Would set retention for {log_group_name} to {retention_days} days")
            return True

        log(f"Setting retention for {log_group_name} to {retention_days} days")
        logs_client.put_retention_policy(
            logGroupName=log_group_name,
            retentionInDays=retention_days
        )
        log(f"Successfully set retention for {log_group_name}")
        return True

    except ClientError as e:
        log(f"Failed to set retention for {log_group_name}: {e}")
        return False


def delete_log_group(logs_client, log_group_name: str, dry_run: bool) -> bool:
    """Delete a log group."""
    try:
        if dry_run:
            log(f"DRY RUN: Would delete log group {log_group_name}")
            return True

        log(f"Deleting log group {log_group_name}")
        logs_client.delete_log_group(logGroupName=log_group_name)
        log(f"Successfully deleted log group {log_group_name}")
        return True

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'ResourceNotFoundException':
            log(f"Log group {log_group_name} was already deleted")
            return True
        else:
            log(f"Failed to delete log group {log_group_name}: {e}")
            return False


def send_alert(webhook: str, optimization_results: List[Dict], total_savings: float,
               actions_taken: Dict) -> None:
    """Send CloudWatch logs optimization results to webhook."""
    if not optimization_results:
        return

    # Count issues by type and priority
    issue_counts = {}
    priority_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}

    for result in optimization_results:
        issue_type = result.get('issue_type', 'unknown')
        priority = result.get('priority', 'LOW')

        issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
        priority_counts[priority] += 1

    total_storage = sum(result.get('stored_gb', 0) for result in optimization_results)

    message_lines = [
        f"CloudWatch Logs Optimization Report",
        f"",
        f"Found {len(optimization_results)} optimization opportunities",
        f"Total analyzed storage: {total_storage:,.2f} GB",
        f"Potential monthly savings: ${total_savings:.2f}",
    ]

    if actions_taken['policies_set'] > 0 or actions_taken['groups_deleted'] > 0:
        message_lines.extend([
            f"",
            f"Actions taken:",
            f"  Retention policies set: {actions_taken['policies_set']}",
            f"  Log groups deleted: {actions_taken['groups_deleted']}"
        ])

    message_lines.extend([
        f"",
        f"Issue breakdown:",
        f"  High priority: {priority_counts['HIGH']}",
        f"  Medium priority: {priority_counts['MEDIUM']}",
        f"  Low priority: {priority_counts['LOW']}"
    ])

    # Show issue type breakdown
    if issue_counts:
        message_lines.append("")
        message_lines.append("Issue types:")
        for issue_type, count in issue_counts.items():
            issue_name = {
                'no_retention': 'No retention policy',
                'excessive_retention': 'Excessive retention',
                'inactive_group': 'Inactive log groups',
                'empty_group': 'Empty log groups'
            }.get(issue_type, issue_type)
            message_lines.append(f"  - {issue_name}: {count}")

    # Show sample high-priority issues
    high_priority = [r for r in optimization_results if r.get('priority') == 'HIGH']
    if high_priority:
        message_lines.append("")
        message_lines.append("High-Priority Issues:")
        for issue in high_priority[:5]:  # Show first 5
            message_lines.append(
                f"- {issue['log_group_name']} in {issue['region']}: "
                f"{issue['description']}"
            )
        if len(high_priority) > 5:
            message_lines.append(f"... and {len(high_priority) - 5} more high-priority issues")

    message_lines.extend([
        f"",
        f"CloudWatch Logs accumulate storage costs over time",
        f"Set appropriate retention policies to control costs",
        f"Regular cleanup of unused log groups saves money"
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
    log("Starting CloudWatch logs optimization")

    # Configuration
    regions = get_regions()
    set_retention_policies = os.getenv("SET_RETENTION_POLICIES", "false").lower() == "true"
    delete_empty_groups = os.getenv("DELETE_EMPTY_GROUPS", "false").lower() == "true"
    empty_group_days = int(os.getenv("EMPTY_GROUP_DAYS", "30"))
    exclude_patterns = [p.strip() for p in os.getenv("EXCLUDE_PATTERNS", "").split(",") if p.strip()]
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    webhook = os.getenv("ALERT_WEBHOOK")

    log(f"Scanning regions: {', '.join(regions)}")
    log(f"Set retention policies: {set_retention_policies}")
    log(f"Delete empty groups: {delete_empty_groups}")
    log(f"Empty group threshold: {empty_group_days} days")
    log(f"Exclude patterns: {exclude_patterns if exclude_patterns else 'None'}")
    log(f"Dry run mode: {dry_run}")

    all_opportunities = []
    total_potential_savings = 0.0
    actions_taken = {'policies_set': 0, 'groups_deleted': 0}

    try:
        for region in regions:
            # Create CloudWatch Logs client
            logs_client = boto3.client('logs', region_name=region)

            # Analyze log groups
            opportunities, savings = analyze_log_groups(
                logs_client, region, exclude_patterns, empty_group_days
            )

            all_opportunities.extend(opportunities)
            total_potential_savings += savings

            # Take actions based on configuration
            for opportunity in opportunities:
                issue_type = opportunity['issue_type']
                log_group_name = opportunity['log_group_name']

                if issue_type in ['no_retention', 'excessive_retention'] and set_retention_policies:
                    suggested_retention = opportunity.get('suggested_retention')
                    if suggested_retention and set_log_retention(logs_client, log_group_name, suggested_retention, dry_run):
                        actions_taken['policies_set'] += 1

                elif issue_type in ['inactive_group', 'empty_group'] and delete_empty_groups:
                    if delete_log_group(logs_client, log_group_name, dry_run):
                        actions_taken['groups_deleted'] += 1

        # Summary
        log(f"")
        log(f"=== CLOUDWATCH LOGS OPTIMIZATION SUMMARY ===")
        log(f"Total optimization opportunities: {len(all_opportunities)}")
        log(f"Potential monthly savings: ${total_potential_savings:.2f}")

        # Break down by issue type
        if all_opportunities:
            issue_counts = {}
            for opp in all_opportunities:
                issue_type = opp['issue_type']
                issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1

            log("Issues by type:")
            for issue_type, count in issue_counts.items():
                log(f"  {issue_type}: {count}")

        # Actions taken
        if actions_taken['policies_set'] > 0:
            log(f"Retention policies set: {actions_taken['policies_set']}")
        if actions_taken['groups_deleted'] > 0:
            log(f"Log groups deleted: {actions_taken['groups_deleted']}")

        # Send alerts
        if webhook and (all_opportunities or actions_taken['policies_set'] > 0 or actions_taken['groups_deleted'] > 0):
            send_alert(webhook, all_opportunities, total_potential_savings, actions_taken)

        return 0

    except NoCredentialsError:
        log("ERROR: AWS credentials not configured")
        return 1
    except Exception as exc:
        log(f"CloudWatch logs optimization failed: {exc}")
        return 1

    log("CloudWatch logs optimization completed")


if __name__ == "__main__":
    sys.exit(main())
