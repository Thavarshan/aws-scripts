# EBS Snapshot Cleanup Script

Automatically clean up old EBS snapshots based on flexible retention policies to reduce storage costs.

## Overview

The `ebs_snapshot_cleanup.py` script manages EBS snapshots using configurable retention policies. EBS snapshots cost $0.05 per GB per month and can accumulate quickly with automated backup systems, especially if no cleanup policies are in place.

## Key Benefits

- **Reduce Storage Costs**: EBS snapshots can be expensive over time
- **Flexible Retention**: Different policies for daily, weekly, and monthly snapshots
- **Safe Operations**: Minimum age requirements and tag-based exclusions
- **Cost Transparency**: Shows potential monthly savings

## Features

- **Intelligent Retention**: Keep daily, weekly, and monthly snapshots
- **Tag-based Exclusion**: Protect important snapshots from cleanup
- **Age-based Safety**: Minimum age before deletion consideration
- **Cost Calculation**: Estimates monthly storage savings
- **Multi-region Support**: Clean up across all AWS regions

## Prerequisites

**AWS IAM Permissions:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeSnapshots",
                "ec2:DeleteSnapshot"
            ],
            "Resource": "*"
        }
    ]
}
```

## Retention Logic

The script implements a 3-tier retention strategy:

1. **Daily Retention**: Keep all snapshots for X days (default: 7)
2. **Weekly Retention**: Keep Monday snapshots for X weeks (default: 4)
3. **Monthly Retention**: Keep first-of-month snapshots for X months (default: 3)

**Example with defaults:**
- Keep daily snapshots for 7 days
- Keep weekly snapshots for 4 weeks (28 days total)
- Keep monthly snapshots for 3 months (90 days total)

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DAILY_RETENTION_DAYS` | `7` | Keep daily snapshots for X days |
| `WEEKLY_RETENTION_WEEKS` | `4` | Keep weekly snapshots for X weeks |
| `MONTHLY_RETENTION_MONTHS` | `3` | Keep monthly snapshots for X months |
| `MIN_SNAPSHOT_AGE_DAYS` | `1` | Minimum age before deletion |
| `EXCLUDE_TAGS` | None | Tag keys to exclude from cleanup |
| `COST_THRESHOLD` | `1.0` | Minimum savings to trigger alerts |
| `DRY_RUN` | `false` | Test mode without deleting |

## Usage Examples

**Analyze without deleting:**
```bash
export DRY_RUN="true"
python ebs_snapshot_cleanup.py
```

**Conservative cleanup (longer retention):**
```bash
export DAILY_RETENTION_DAYS="14"
export WEEKLY_RETENTION_WEEKS="8"
export MONTHLY_RETENTION_MONTHS="6"
python ebs_snapshot_cleanup.py
```

**Exclude tagged snapshots:**
```bash
export EXCLUDE_TAGS="DoNotDelete,Production,Backup"
python ebs_snapshot_cleanup.py
```

## Example Output

```
[2024-01-15T10:30:15Z] Starting EBS snapshot cleanup
[2024-01-15T10:30:15Z] Retention policy: 7 daily, 4 weekly, 3 monthly
[2024-01-15T10:30:16Z] Found 45 snapshot(s) in us-east-1
[2024-01-15T10:30:16Z]   snap-1234567890abcdef0 (DB-Backup-Daily): KEEP - 20 GB, 3 days old (retention policy)
[2024-01-15T10:30:16Z]   snap-0987654321fedcba0 (Web-Server-Old): DELETE - 8 GB, 45 days old, $0.40/month
[2024-01-15T10:30:16Z]   snap-1122334455667788 (Log-Archive): DELETE - 15 GB, 120 days old, $0.75/month
[2024-01-15T10:30:17Z] Deleting 12 snapshot(s) in us-east-1...
[2024-01-15T10:30:20Z] Successfully deleted snap-0987654321fedcba0
[2024-01-15T10:30:21Z] Total size: 180 GB
[2024-01-15T10:30:21Z] Monthly savings: $9.00
```

## Retention Policy Examples

**Aggressive cleanup (short retention):**
```bash
export DAILY_RETENTION_DAYS="3"
export WEEKLY_RETENTION_WEEKS="2"
export MONTHLY_RETENTION_MONTHS="1"
```

**Conservative approach (long retention):**
```bash
export DAILY_RETENTION_DAYS="30"
export WEEKLY_RETENTION_WEEKS="12"
export MONTHLY_RETENTION_MONTHS="12"
```

**Development environment:**
```bash
export DAILY_RETENTION_DAYS="1"
export WEEKLY_RETENTION_WEEKS="0"
export MONTHLY_RETENTION_MONTHS="0"
```

## Safety Features

1. **Minimum Age Protection**: Won't delete very recent snapshots
2. **Tag-based Exclusion**: Protect critical snapshots with tags
3. **Dry-run Mode**: Test policies before applying
4. **Detailed Logging**: See exactly what will be deleted

## Cost Impact

For a typical environment with automated daily backups:
- **Before**: 365 snapshots × 10 GB × $0.05 = $182.50/month
- **After** (7/4/3 retention): ~30 snapshots × 10 GB × $0.05 = $15.00/month
- **Savings**: $167.50/month (92% reduction)

## Integration

This script works well with:
- **Budget Monitor**: Can be triggered when storage costs spike
- **Automated Backups**: Clean up after backup systems
- **Monitoring**: Use webhook alerts for visibility
