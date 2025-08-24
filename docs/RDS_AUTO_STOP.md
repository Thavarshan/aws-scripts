# RDS Auto-Stop Script

Automatically stop RDS database instances based on tags to reduce compute costs during off-hours.

## Overview

The `rds_auto_stop.py` script automatically stops RDS instances tagged with specific key/value pairs (default: `auto-off=true`). RDS instances can be significantly more expensive than EC2 instances, making automated stopping during off-hours a high-impact cost optimization strategy.

## Key Benefits

- **High Cost Impact**: RDS instances often cost $50-200+ per month
- **Preserve Data**: Stopping RDS only pauses compute, storage remains intact
- **Flexible Control**: Tag-based targeting with safety exclusions
- **Multi-Engine Support**: Works with MySQL, PostgreSQL, Oracle, SQL Server

## Features

- **Tag-based Filtering**: Only stops instances you explicitly tag
- **Safety Controls**: Skip Multi-AZ, read replicas, or cluster instances
- **Multi-region Support**: Scan and stop across AWS regions
- **Cost Estimation**: Calculate potential monthly savings
- **Detailed Reporting**: Comprehensive webhook notifications

## Prerequisites

**AWS IAM Permissions:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "rds:DescribeDBInstances",
                "rds:StopDBInstance",
                "rds:ListTagsForResource"
            ],
            "Resource": "*"
        }
    ]
}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TAG_KEY` | `auto-off` | Tag key to look for |
| `TAG_VALUE` | `true` | Tag value to match |
| `SKIP_MULTI_AZ` | `false` | Skip Multi-AZ instances |
| `SKIP_READ_REPLICAS` | `false` | Skip read replica instances |
| `SKIP_CLUSTER_INSTANCES` | `false` | Skip Aurora cluster members |
| `DRY_RUN` | `false` | Test mode without stopping |
| `ALERT_WEBHOOK` | None | Webhook for notifications |

## Usage Examples

**Tag RDS instances for auto-stop:**
```bash
aws rds add-tags-to-resource \
  --resource-name arn:aws:rds:us-east-1:123456789012:db:mydb \
  --tags Key=auto-off,Value=true
```

**Safe test run:**
```bash
export DRY_RUN="true"
python rds_auto_stop.py
```

**Skip critical instances:**
```bash
export SKIP_MULTI_AZ="true"
export SKIP_READ_REPLICAS="true"
python rds_auto_stop.py
```

## Safety Features

### Automatic Exclusions

The script automatically skips instances that shouldn't be stopped:

1. **Multi-AZ Instances** (if `SKIP_MULTI_AZ=true`)
   - High-availability setups that may serve critical traffic

2. **Read Replicas** (if `SKIP_READ_REPLICAS=true`)
   - May be serving read traffic from applications

3. **Aurora Cluster Members** (if `SKIP_CLUSTER_INSTANCES=true`)
   - Part of cluster configurations

4. **Non-available Instances**
   - Already stopped, stopping, or in maintenance

## Example Output

```
[2024-01-15T14:30:15Z] Starting RDS auto-stop script
[2024-01-15T14:30:15Z] Looking for tag: auto-off=true
[2024-01-15T14:30:16Z] Found 3 matching RDS instance(s) in us-east-1
[2024-01-15T14:30:16Z] Skipping prod-db-1 (db.r5.large): Multi-AZ instance (high availability)
[2024-01-15T14:30:17Z] Stopping RDS instance dev-db (db.t3.medium, mysql) in us-east-1...
[2024-01-15T14:30:18Z] Stopping RDS instance test-postgres (db.t3.small, postgres) in us-east-1...
[2024-01-15T14:30:18Z] Total instances stopped: 2
[2024-01-15T14:30:18Z] Estimated monthly savings: $87.60
```

## Cost Impact Examples

**db.t3.medium (MySQL)**: ~$58/month → Stop 12 hours/day = **$29/month savings**
**db.r5.large (PostgreSQL)**: ~$182/month → Stop 12 hours/day = **$91/month savings**
**db.r5.xlarge (Oracle)**: ~$365/month → Stop 12 hours/day = **$182/month savings**

## Important Notes

### What Happens When RDS Stops?
- **Compute billing stops** (major cost component)
- **Storage billing continues** (EBS, backups, snapshots)
- **Database data preserved** completely
- **Configuration maintained** (security groups, parameter groups, etc.)

### Restart Process
```bash
# Restart manually via CLI
aws rds start-db-instance --db-instance-identifier my-database

# Restart via AWS Console
# RDS → Databases → Select instance → Actions → Start
```

### Limitations
- **No hibernation**: RDS doesn't support hibernation like EC2
- **Startup time**: 2-5 minutes to restart depending on instance size
- **Connection drops**: Applications must handle reconnection
- **Maintenance windows**: May prevent stopping during maintenance

## Webhook Notifications

The script sends detailed notifications showing:
- Which instances were stopped/skipped and why
- Estimated monthly savings
- Instance details (class, engine, region)

```json
{
  "text": "RDS Auto-Stop Summary:\n\nEstimated monthly savings: $87.60\n\n- us-east-1 - dev-db (db.t3.medium) - stopping (requested)\n- us-east-1 - prod-db-1 (db.r5.large) - skipped (Multi-AZ instance)\n\nStorage costs continue while instances are stopped\nRestart instances when needed"
}
```

## Integration with Budget Monitor

The budget monitor can automatically trigger RDS auto-stop during budget emergencies:
- **90% of budget**: Trigger RDS auto-stop
- **100% of budget**: Trigger all cost-saving scripts

## Best Practices

1. **Start with dev/test**: Tag non-production databases first
2. **Monitor applications**: Ensure apps handle DB disconnections gracefully
3. **Coordinate with team**: Communicate stopping schedules
4. **Use automation**: Combine with scheduling for consistent savings
5. **Monitor costs**: Track actual savings vs. estimates
