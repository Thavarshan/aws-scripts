#!/usr/bin/env python3
"""
budget_monitor.py -- Monitor AWS monthly budget and trigger cost-saving actions.

This script monitors your AWS spending against a monthly budget limit and can
automatically trigger cost-saving scripts (like ec2_auto_off.py) when spending
thresholds are reached. It uses the AWS Cost Explorer API to get current
month-to-date spending and compares it against configurable budget thresholds.

The script supports multiple threshold levels:
- Warning (75% of budget): Send alert only
- Critical (90% of budget): Send alert + optionally trigger scripts
- Emergency (100% of budget): Send urgent alert + trigger all cost-saving scripts

Environment variables:
    MONTHLY_BUDGET: Monthly budget limit in USD (default: "10.00").
    WARNING_THRESHOLD: Percentage of budget for warning alert (default: "75").
    CRITICAL_THRESHOLD: Percentage of budget for critical alert (default: "90").
    EMERGENCY_THRESHOLD: Percentage of budget for emergency alert (default: "100").
    ENABLE_SCRIPT_TRIGGERS: If "true", will trigger other scripts when thresholds hit.
    DRY_RUN: If "true", logs actions without actually triggering scripts.
    ALERT_WEBHOOK: Optional HTTP endpoint for notifications.
    AWS_ACCOUNT_ID: Optional AWS account ID (auto-detected if not provided).

Usage:
    python budget_monitor.py
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import requests


def log(msg: str) -> None:
    """Prints a timestamped message to stdout."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}")


def get_current_month_spend() -> Tuple[float, str]:
    """
    Get current month-to-date spending using Cost Explorer API.
    Returns (spend_amount, currency) tuple.
    """
    try:
        # Cost Explorer is only available in us-east-1
        cost_client = boto3.client('ce', region_name='us-east-1')

        # Get first day of current month and today
        now = datetime.utcnow()
        start_date = now.replace(day=1).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')

        log(f"Fetching spending data from {start_date} to {end_date}")

        response = cost_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['BlendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ]
        )

        total_cost = 0.0
        currency = 'USD'

        for result in response['ResultsByTime']:
            for group in result['Groups']:
                amount = float(group['Metrics']['BlendedCost']['Amount'])
                total_cost += amount
                currency = group['Metrics']['BlendedCost']['Unit']

                # Log service-level costs for visibility
                service = group['Keys'][0] if group['Keys'] else 'Unknown'
                if amount > 0.01:  # Only log costs > $0.01
                    log(f"  {service}: ${amount:.2f}")

        return total_cost, currency

    except NoCredentialsError:
        log("ERROR: AWS credentials not configured")
        raise
    except ClientError as e:
        error_code = e.response['Error'].get('Code', 'Unknown')
        if error_code == 'UnauthorizedOperation':
            log("ERROR: Insufficient permissions for Cost Explorer API")
            log("Required IAM permission: ce:GetCostAndUsage")
        else:
            log(f"ERROR: Failed to get cost data: {e}")
        raise


def calculate_thresholds(budget: float) -> Dict[str, Dict[str, float]]:
    """Calculate spending thresholds based on budget."""
    warning_pct = float(os.getenv("WARNING_THRESHOLD", "75"))
    critical_pct = float(os.getenv("CRITICAL_THRESHOLD", "90"))
    emergency_pct = float(os.getenv("EMERGENCY_THRESHOLD", "100"))

    return {
        'warning': {
            'threshold': budget * (warning_pct / 100),
            'percentage': warning_pct
        },
        'critical': {
            'threshold': budget * (critical_pct / 100),
            'percentage': critical_pct
        },
        'emergency': {
            'threshold': budget * (emergency_pct / 100),
            'percentage': emergency_pct
        }
    }


def determine_alert_level(current_spend: float, thresholds: Dict[str, Dict[str, float]]) -> Optional[str]:
    """Determine the appropriate alert level based on current spending."""
    if current_spend >= thresholds['emergency']['threshold']:
        return 'emergency'
    elif current_spend >= thresholds['critical']['threshold']:
        return 'critical'
    elif current_spend >= thresholds['warning']['threshold']:
        return 'warning'
    return None


def send_alert(webhook: str, alert_level: str, current_spend: float, budget: float,
               currency: str, threshold_info: Dict[str, float]) -> None:
    """Send budget alert to webhook."""
    percentage_used = (current_spend / budget) * 100 if budget > 0 else 0

    # Choose emoji and message based on alert level
    emoji_map = {
        'warning': 'WARNING',
        'critical': 'CRITICAL',
        'emergency': 'EMERGENCY'
    }

    prefix = emoji_map.get(alert_level, 'ALERT')
    level_name = alert_level.upper()

    message_lines = [
        f"{prefix} - AWS Budget {level_name} Alert",
        f"",
        f"Current spend: {currency} ${current_spend:.2f}",
        f"Monthly budget: {currency} ${budget:.2f}",
        f"Usage: {percentage_used:.1f}% of budget",
        f"Threshold: {threshold_info['percentage']:.0f}% (${threshold_info['threshold']:.2f})",
        f"",
        f"Month-to-date as of {datetime.utcnow().strftime('%Y-%m-%d')}"
    ]

    if alert_level in ['critical', 'emergency']:
        message_lines.extend([
            f"",
            f"Consider running cost-saving measures:",
            f"- Stop non-essential EC2 instances",
            f"- Review running services",
            f"- Check for unused resources"
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


def trigger_cost_saving_scripts(alert_level: str, dry_run: bool) -> List[Dict[str, str]]:
    """Trigger cost-saving scripts based on alert level."""
    scripts_triggered = []

    # Define which scripts to run for each alert level
    script_actions = {
        'critical': [
            {
                'name': 'EC2 Auto-Off',
                'command': ['python3', 'ec2_auto_off.py'],
                'description': 'Stop tagged EC2 instances'
            }
        ],
        'emergency': [
            {
                'name': 'EC2 Auto-Off',
                'command': ['python3', 'ec2_auto_off.py'],
                'description': 'Stop tagged EC2 instances'
            }
            # Future: Add more aggressive cost-saving scripts here
        ]
    }

    actions = script_actions.get(alert_level, [])

    for action in actions:
        log(f"Triggering {action['name']}: {action['description']}")

        try:
            if dry_run:
                log(f"DRY RUN: Would execute: {' '.join(action['command'])}")
                scripts_triggered.append({
                    'name': action['name'],
                    'status': 'dry-run',
                    'description': action['description']
                })
            else:
                # Set environment variables for the triggered script
                env = os.environ.copy()
                env['DRY_RUN'] = 'false'  # Make sure triggered scripts actually execute

                result = subprocess.run(
                    action['command'],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                    env=env
                )

                if result.returncode == 0:
                    log(f"{action['name']} completed successfully")
                    scripts_triggered.append({
                        'name': action['name'],
                        'status': 'success',
                        'description': action['description']
                    })
                else:
                    log(f"{action['name']} failed with return code {result.returncode}")
                    log(f"Error output: {result.stderr}")
                    scripts_triggered.append({
                        'name': action['name'],
                        'status': 'failed',
                        'description': action['description'],
                        'error': result.stderr
                    })

        except subprocess.TimeoutExpired:
            log(f"{action['name']} timed out after 5 minutes")
            scripts_triggered.append({
                'name': action['name'],
                'status': 'timeout',
                'description': action['description']
            })
        except Exception as exc:
            log(f"Failed to execute {action['name']}: {exc}")
            scripts_triggered.append({
                'name': action['name'],
                'status': 'error',
                'description': action['description'],
                'error': str(exc)
            })

    return scripts_triggered


def main() -> int:
    """Main function."""
    log("Starting AWS budget monitoring")

    # Configuration
    budget = float(os.getenv("MONTHLY_BUDGET", "10.00"))
    enable_script_triggers = os.getenv("ENABLE_SCRIPT_TRIGGERS", "false").lower() == "true"
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    webhook = os.getenv("ALERT_WEBHOOK")

    log(f"Monthly budget: ${budget:.2f}")
    log(f"Script triggers enabled: {enable_script_triggers}")
    log(f"Dry run mode: {dry_run}")

    try:
        # Get current spending
        current_spend, currency = get_current_month_spend()
        log(f"Current month-to-date spend: {currency} ${current_spend:.2f}")

        # Calculate thresholds
        thresholds = calculate_thresholds(budget)

        # Check if we need to alert
        alert_level = determine_alert_level(current_spend, thresholds)

        if alert_level:
            log(f"Budget {alert_level.upper()} threshold exceeded!")

            # Send webhook alert if configured
            if webhook:
                send_alert(webhook, alert_level, current_spend, budget,
                          currency, thresholds[alert_level])
            else:
                log("No webhook configured, skipping alert notification")

            # Trigger cost-saving scripts if enabled and threshold warrants it
            scripts_triggered = []
            if enable_script_triggers and alert_level in ['critical', 'emergency']:
                log("Triggering cost-saving scripts...")
                scripts_triggered = trigger_cost_saving_scripts(alert_level, dry_run)

            # Summary
            percentage_used = (current_spend / budget) * 100 if budget > 0 else 0
            log(f"Budget summary: ${current_spend:.2f} / ${budget:.2f} ({percentage_used:.1f}%)")

            if scripts_triggered:
                log("Scripts triggered:")
                for script in scripts_triggered:
                    log(f"  - {script['name']}: {script['status']}")

        else:
            percentage_used = (current_spend / budget) * 100 if budget > 0 else 0
            log(f"Budget is within safe limits: ${current_spend:.2f} / ${budget:.2f} ({percentage_used:.1f}%)")

            # Show threshold status
            for level, info in thresholds.items():
                remaining = info['threshold'] - current_spend
                if remaining > 0:
                    log(f"  {level.capitalize()} threshold (${info['threshold']:.2f}): ${remaining:.2f} remaining")

    except Exception as exc:
        log(f"Budget monitoring failed: {exc}")
        return 1

    log("Budget monitoring completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
