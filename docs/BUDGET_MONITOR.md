# Budget Monitor Script

Monitor your AWS monthly spending and automatically trigger cost-saving actions when budget thresholds are exceeded.

## Overview

The `budget_monitor.py` script uses the AWS Cost Explorer API to track your month-to-date spending against a configurable budget limit. When spending reaches certain thresholds, it can send alerts and automatically trigger other scripts in the project (like `ec2_auto_off.py`) to help control costs.

## Features

- **Real-time budget monitoring** using AWS Cost Explorer API
- **Multiple alert levels** with configurable thresholds
- **Automatic script triggering** when critical thresholds are reached
- **Service-level cost breakdown** for visibility into spending
- **Webhook notifications** to Slack, Discord, or other endpoints
- **Dry-run mode** for safe testing
- **Scheduled monitoring** via GitHub Actions

## Alert Levels

| Level | Default Threshold | Actions |
|-------|-------------------|---------|
| **Warning** | 75% of budget | Send alert notification only |
| **Critical** | 90% of budget | Send alert + trigger EC2 auto-off script |
| **Emergency** | 100% of budget | Send urgent alert + trigger all cost-saving scripts |

## Prerequisites

1. **AWS Account** with Cost Explorer enabled
2. **AWS IAM User** with permissions:
   - `ce:GetCostAndUsage` (for Cost Explorer API)
   - Plus permissions for any scripts that may be triggered (e.g., EC2 permissions for auto-off)
3. **GitHub repository** with secrets configured

## Setup Instructions

### 1. Configure GitHub Repository Variables

Go to **Settings > Secrets and variables > Actions** and add these **Variables**:

**Budget Configuration:**
- `MONTHLY_BUDGET`: Your monthly budget in USD (default: `10.00`)
- `WARNING_THRESHOLD`: Warning percentage (default: `75`)
- `CRITICAL_THRESHOLD`: Critical percentage (default: `90`)
- `EMERGENCY_THRESHOLD`: Emergency percentage (default: `100`)

**Script Control:**
- `ENABLE_SCRIPT_TRIGGERS`: Enable automatic script triggering (default: `true`)

**Example values for $10 budget:**
- `MONTHLY_BUDGET`: `10.00`
- `WARNING_THRESHOLD`: `75` (alert at $7.50)
- `CRITICAL_THRESHOLD`: `90` (alert + trigger scripts at $9.00)
- `EMERGENCY_THRESHOLD`: `100` (urgent alert + all scripts at $10.00)

### 2. GitHub Secrets

Your existing secrets work for this script too:
- `AWS_ACCESS_KEY_ID`: Your AWS access key ID
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key
- `ALERT_WEBHOOK`: Webhook URL for notifications

### 3. IAM Permissions

Add the Cost Explorer permission to your AWS IAM user:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ce:GetCostAndUsage"
            ],
            "Resource": "*"
        }
    ]
}
```

## Configuration Options

The script uses environment variables for configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `MONTHLY_BUDGET` | `10.00` | Monthly budget limit in USD |
| `WARNING_THRESHOLD` | `75` | Percentage for warning alerts |
| `CRITICAL_THRESHOLD` | `90` | Percentage for critical alerts + script triggers |
| `EMERGENCY_THRESHOLD` | `100` | Percentage for emergency alerts |
| `ENABLE_SCRIPT_TRIGGERS` | `true` | Whether to trigger scripts automatically |
| `DRY_RUN` | `false` | Test mode - log actions without executing |
| `ALERT_WEBHOOK` | None | HTTP endpoint for notifications |

## Local Usage

You can run the script locally to check your current budget status:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export MONTHLY_BUDGET="10.00"
export DRY_RUN="true"  # Test mode

# Run the script
python budget_monitor.py
```

## GitHub Actions Workflow

The budget monitor runs automatically:

- **Schedule**: Every 6 hours (0, 6, 12, 18 UTC) to monitor throughout the day
- **Manual trigger**: Run on-demand from Actions tab
- **Smart triggering**: Only triggers cost-saving scripts when critical thresholds are hit

## Script Integration

When critical or emergency thresholds are reached, the budget monitor can automatically trigger:

### Currently Supported:
- **EC2 Auto-Off** (`ec2_auto_off.py`): Stops tagged EC2 instances

### Future Additions:
You can extend the script to trigger additional cost-saving actions:
- RDS instance stopping
- EBS snapshot cleanup
- Unused EIP release
- CloudWatch log retention optimization

## Example Output

```
[2024-01-15T10:30:15Z] Starting AWS budget monitoring
[2024-01-15T10:30:15Z] Monthly budget: $10.00
[2024-01-15T10:30:15Z] Script triggers enabled: true
[2024-01-15T10:30:16Z] Fetching spending data from 2024-01-01 to 2024-01-15
[2024-01-15T10:30:17Z]   Amazon Elastic Compute Cloud - Compute: $8.45
[2024-01-15T10:30:17Z]   Amazon Simple Storage Service: $0.23
[2024-01-15T10:30:17Z] Current month-to-date spend: USD $8.68
[2024-01-15T10:30:17Z] Budget is within safe limits: $8.68 / $10.00 (86.8%)
[2024-01-15T10:30:17Z]   Warning threshold ($7.50): exceeded
[2024-01-15T10:30:17Z]   Critical threshold ($9.00): $0.32 remaining
[2024-01-15T10:30:17Z]   Emergency threshold ($10.00): $1.32 remaining
[2024-01-15T10:30:17Z] Budget monitoring completed
```

## Webhook Notifications

When thresholds are exceeded, webhook alerts include:

```
AWS Budget CRITICAL Alert

Current spend: USD $9.15
Monthly budget: USD $10.00
Usage: 91.5% of budget
Threshold: 90% ($9.00)

Month-to-date as of 2024-01-15

Consider running cost-saving measures:
- Stop non-essential EC2 instances
- Review running services
- Check for unused resources
```

## Monitoring Schedule

The default schedule runs every 6 hours:
- **00:00 UTC**: Daily budget check
- **06:00 UTC**: Morning check
- **12:00 UTC**: Midday check
- **18:00 UTC**: Evening check

This provides good coverage without excessive API calls.

## Troubleshooting

1. **"Insufficient permissions" error**: Add `ce:GetCostAndUsage` permission to your IAM user
2. **"No cost data found"**: Cost Explorer may take 24-48 hours to show new account data
3. **Script triggers not working**: Check that `ENABLE_SCRIPT_TRIGGERS=true` is set
4. **Threshold not triggering**: Verify your threshold percentages are correct

## Cost Management Strategy

This budget monitor works best as part of a comprehensive cost management approach:

1. **Proactive**: EC2 auto-off runs on schedule (prevention)
2. **Reactive**: Budget monitor triggers when spending spikes (emergency brake)
3. **Visibility**: Both scripts provide detailed cost breakdowns and alerts

Together, they provide both predictable daily savings and emergency cost control!
