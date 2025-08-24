# EC2 Auto-Off Script

Automatically stop or hibernate EC2 instances based on tags using Python and GitHub Actions.

## Overview

The `ec2_auto_off.py` script scans one or more AWS regions for EC2 instances tagged with a specific key/value pair (default: `auto-off=true`) and stops or hibernates them. It's designed to run on a schedule via GitHub Actions to help reduce AWS costs by automatically shutting down instances during off-hours.

## Features

- **Tag-based filtering**: Only affects instances with specific tags
- **Multi-region support**: Scan and manage instances across multiple AWS regions
- **Hibernation support**: Option to hibernate instances instead of stopping them
- **Dry-run mode**: Test the script without actually stopping instances
- **Webhook alerts**: Send summaries to Slack, Discord, or other webhook endpoints
- **Scheduled execution**: Runs automatically via GitHub Actions

## Prerequisites

1. **AWS Account** with EC2 instances
2. **AWS IAM User** with permissions to:
   - `ec2:DescribeInstances`
   - `ec2:StopInstances`
3. **GitHub repository** to host the code and run the Actions

## Setup Instructions

### 1. Tag Your EC2 Instances

Add the tag `auto-off=true` to any EC2 instances you want to be automatically stopped:

```bash
aws ec2 create-tags --resources i-1234567890abcdef0 --tags Key=auto-off,Value=true
```

### 2. Configure GitHub Repository Secrets

In your GitHub repository, go to **Settings > Secrets and variables > Actions** and add:

**Repository Secrets:**
- `AWS_ACCESS_KEY_ID`: Your AWS access key ID
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key
- `ALERT_WEBHOOK` (optional): Webhook URL for notifications (Slack, Discord, etc.)

**Repository Variables (optional):**
- `AWS_DEFAULT_REGION`: Default AWS region (e.g., `us-east-1`)
- `REGIONS`: Comma-separated list of regions to scan (e.g., `us-east-1,us-west-2`)
- `TAG_KEY`: Custom tag key (default: `auto-off`)
- `TAG_VALUE`: Custom tag value (default: `true`)
- `HIBERNATE`: Set to `true` to hibernate instead of stop (default: `false`)
- `DRY_RUN`: Set to `true` to test without actually stopping instances (default: `false`)

### 3. Enable GitHub Actions

The workflow is configured to run daily at 14:30 UTC (20:00 Asia/Colombo). You can:
- Wait for the scheduled run
- Manually trigger it from **Actions > EC2 Auto Off > Run workflow**
- Customize the schedule by editing `.github/workflows/ec2-auto-off.yml`

## Configuration Options

The script uses environment variables for configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `REGIONS` | `AWS_DEFAULT_REGION` or `us-east-1` | Comma-separated list of regions to scan |
| `TAG_KEY` | `auto-off` | Tag key to look for |
| `TAG_VALUE` | `true` | Tag value to look for |
| `HIBERNATE` | `false` | Set to `true` to hibernate instead of stop |
| `DRY_RUN` | `false` | Set to `true` to log actions without executing |
| `ALERT_WEBHOOK` | None | HTTP endpoint for notifications |

## Local Usage

You can also run the script locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
export DRY_RUN="true"  # Test mode

# Run the script
python ec2_auto_off.py
```

## Stop vs. Hibernate

### Stop
- Performs a normal shutdown
- Instance state is lost
- You pay for EBS storage only
- Faster to stop and start

### Hibernate
- Suspends the instance to disk
- RAM contents are saved to the EBS root volume
- Instance state is preserved
- You pay for EBS storage + RAM dump storage
- Slower to hibernate and resume
- **Requirements:**
  - Instance must be launched with hibernation enabled
  - Root volume must be encrypted EBS volume
  - Root volume must have enough space for RAM contents
  - Only supported on certain instance types

If hibernation requirements aren't met, the script automatically falls back to a normal stop.

## Webhook Notifications

If you set the `ALERT_WEBHOOK` environment variable, the script will send a summary of actions taken. The webhook receives a JSON payload like:

```json
{
  "text": "EC2 auto-off summary:\n- us-east-1 i-1234567890abcdef0: stopping (requested)\n- us-west-2 i-0987654321fedcba0: hibernating (requested)"
}
```

This format works with Slack and Discord webhooks out of the box.

## Customizing the Schedule

To change when the script runs, edit the cron expression in `.github/workflows/ec2-auto-off.yml`:

```yaml
on:
  schedule:
    # Run every day at 14:30 UTC (20:00 Asia/Colombo)
    - cron: '30 14 * * *'
```

Common cron patterns:
- `0 22 * * *` - Daily at 22:00 UTC
- `0 18 * * 1-5` - Weekdays at 18:00 UTC
- `*/30 * * * *` - Every 30 minutes

## Troubleshooting

1. **No instances found**: Check that instances are tagged correctly and running
2. **Permission denied**: Verify IAM permissions for EC2 operations
3. **Hibernation failed**: Ensure instance meets hibernation requirements
4. **Webhook not working**: Check the webhook URL and format requirements

## Example Output

```
[2024-01-15T14:30:15Z] Scanning region us-east-1 for instances tagged auto-off=true...
[2024-01-15T14:30:16Z] Found 2 matching running instance(s) in us-east-1
[2024-01-15T14:30:16Z] Stopping instance i-1234567890abcdef0 in us-east-1...
[2024-01-15T14:30:17Z] Hibernating instance i-0987654321fedcba0 in us-east-1...
[2024-01-15T14:30:18Z] Finished EC2 auto-off script.
```
