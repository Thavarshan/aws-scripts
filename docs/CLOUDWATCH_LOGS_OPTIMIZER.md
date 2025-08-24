# CloudWatch Logs Optimizer

Manage CloudWatch log retention policies to control storage costs and clean up unused log groups.

## Overview

The `cloudwatch_logs_optimizer.py` script manages CloudWatch log groups to optimize storage costs. CloudWatch Logs can accumulate significant costs over time, especially when log groups have no retention policy (infinite retention) or overly long retention periods. The script automatically sets appropriate retention policies and identifies cleanup opportunities.

## Cost Impact

CloudWatch Logs pricing:
- **Storage**: $0.50 per GB ingested
- **Retention**: $0.03 per GB per month
- **No charges after log expiration**

**Example**: 10 GB of logs with no retention = $0.30/month forever. With 14-day retention = $0.30/month for 14 days, then $0/month.

## Key Benefits

- **Automatic Retention Policies**: Set intelligent retention based on log group names
- **Cost Control**: Prevent infinite log accumulation
- **Unused Group Cleanup**: Remove inactive/empty log groups
- **Smart Defaults**: Different retention for production vs development logs
- **Pattern-based Logic**: Automatically categorize log groups by name patterns

## Features

- **Intelligent Retention Assignment**: Different policies for different log types
- **Inactive Group Detection**: Find log groups with no recent activity
- **Pattern-based Exclusion**: Skip log groups based on name patterns
- **Cost Estimation**: Calculate potential monthly savings
- **Multi-region Support**: Manage logs across all AWS regions
- **Safe Operations**: Comprehensive dry-run testing

## Prerequisites

**AWS IAM Permissions:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:DescribeLogGroups",
                "logs:PutRetentionPolicy",
                "logs:DeleteLogGroup",
                "cloudwatch:GetMetricStatistics"
            ],
            "Resource": "*"
        }
    ]
}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_RETENTION_DAYS` | `14` | Default retention for most logs |
| `CRITICAL_LOG_RETENTION` | `30` | Retention for critical logs (Lambda, etc.) |
| `SET_RETENTION_POLICIES` | `false` | Automatically set retention policies |
| `DELETE_EMPTY_GROUPS` | `false` | Delete inactive log groups |
| `EMPTY_GROUP_DAYS` | `30` | Days of inactivity before deletion |
| `EXCLUDE_PATTERNS` | None | Regex patterns to exclude from management |
| `MIN_SNAPSHOT_AGE_DAYS` | `1` | Minimum age before considering changes |
| `DRY_RUN` | `false` | Test mode without making changes |

## Intelligent Retention Logic

The script automatically determines appropriate retention based on log group names:

### Critical Logs (30 days retention)
- `/aws/lambda/` - Lambda function logs
- `/aws/apigateway/` - API Gateway logs
- `/aws/rds/` - RDS database logs
- `production`, `prod` - Production environment logs
- `security`, `audit` - Security-related logs
- `error` - Error logs

### Debug/Development Logs (7 days retention)
- `debug` - Debug logs
- `development`, `dev` - Development logs
- `test`, `staging` - Test environment logs

### Standard Logs (14 days retention)
- Everything else gets the default retention

## Usage Examples

**Analyze log groups (safe mode):**
```bash
export DRY_RUN="true"
python cloudwatch_logs_optimizer.py
```

**Set retention policies automatically:**
```bash
export SET_RETENTION_POLICIES="true"
export DRY_RUN="true"  # Test first!
python cloudwatch_logs_optimizer.py
```

**Clean up inactive groups:**
```bash
export DELETE_EMPTY_GROUPS="true"
export EMPTY_GROUP_DAYS="60"  # 2 months inactive
export DRY_RUN="true"
python cloudwatch_logs_optimizer.py
```

**Custom retention periods:**
```bash
export DEFAULT_RETENTION_DAYS="7"      # Short retention
export CRITICAL_LOG_RETENTION="90"     # Longer for critical logs
export SET_RETENTION_POLICIES="true"
python cloudwatch_logs_optimizer.py
```

**Exclude specific log groups:**
```bash
export EXCLUDE_PATTERNS="^/aws/cloudtrail/,^/aws/codebuild/"
export SET_RETENTION_POLICIES="true"
python cloudwatch_logs_optimizer.py
```

## Example Output

```
[2024-01-15T08:30:15Z] Starting CloudWatch logs optimization
[2024-01-15T08:30:15Z] Retention policy: 14 daily, 4 weekly, 3 monthly
[2024-01-15T08:30:16Z] Analyzing CloudWatch log groups in region us-east-1...
[2024-01-15T08:30:16Z] Found 25 log group(s) in us-east-1

Log Group Analysis:
[2024-01-15T08:30:17Z]   /aws/lambda/my-function: No retention policy (infinite retention) - HIGH PRIORITY
[2024-01-15T08:30:17Z]   /aws/apigateway/api-logs: No retention policy - HIGH PRIORITY
[2024-01-15T08:30:17Z]   /aws/ec2/development-logs: Retention 365 days - MEDIUM PRIORITY (excessive)
[2024-01-15T08:30:17Z]   /my-app/debug-logs: No activity for 45 days - LOW PRIORITY (cleanup candidate)

Actions Taken:
[2024-01-15T08:30:18Z] DRY RUN: Would set retention for /aws/lambda/my-function to 30 days
[2024-01-15T08:30:18Z] DRY RUN: Would set retention for /aws/apigateway/api-logs to 30 days
[2024-01-15T08:30:18Z] DRY RUN: Would delete log group /my-app/debug-logs (inactive)

=== CLOUDWATCH LOGS OPTIMIZATION SUMMARY ===
Total optimization opportunities: 15
Potential monthly savings: $12.50
High priority issues: 8 (no retention policy)
Medium priority issues: 4 (excessive retention)
Low priority issues: 3 (inactive groups)
```

## Retention Strategy Examples

### Conservative Approach
```bash
export DEFAULT_RETENTION_DAYS="30"
export CRITICAL_LOG_RETENTION="90"
```
Good for: Production environments, compliance requirements

### Aggressive Cost Savings
```bash
export DEFAULT_RETENTION_DAYS="7"
export CRITICAL_LOG_RETENTION="14"
```
Good for: Development environments, cost-sensitive projects

### Balanced Approach
```bash
export DEFAULT_RETENTION_DAYS="14"     # Default
export CRITICAL_LOG_RETENTION="30"     # Default
```
Good for: Most use cases, balanced cost/retention

## Common Optimization Patterns

### 1. No Retention Policy (Highest Priority)
**Problem**: Logs accumulate forever, costs grow indefinitely
**Solution**: Apply intelligent retention based on log group type
```bash
# Before: /aws/lambda/my-function (no retention) = $0.30/month forever
# After: 30-day retention = $0.30/month for 30 days, then $0/month
```

### 2. Excessive Retention (Medium Priority)
**Problem**: Logs kept longer than necessary
**Solution**: Reduce retention to appropriate periods
```bash
# Before: Development logs with 365-day retention
# After: Development logs with 7-day retention = 98% cost reduction
```

### 3. Inactive Log Groups (Low Priority)
**Problem**: Log groups with no activity still consume space
**Solution**: Delete groups with no recent log entries
```bash
# Groups with no activity for 30+ days = full cost recovery
```

## Integration Features

### Budget Monitor Integration
When budget thresholds are hit, automatically trigger log optimization:
```bash
# Emergency cost reduction via log cleanup
export SET_RETENTION_POLICIES="true"
export DELETE_EMPTY_GROUPS="true"
export DEFAULT_RETENTION_DAYS="7"
```

### Webhook Notifications
Comprehensive reports include:
- Number of log groups analyzed
- Issues found by priority level
- Potential monthly savings
- Actions taken (policies set, groups deleted)
- Sample high-priority issues

### Scheduled Optimization
Monthly GitHub Actions workflow:
- **Analysis Mode**: Generate optimization reports
- **Management Mode**: Apply retention policies automatically

## Cost Calculation Examples

### Small Environment (5GB logs/month)
- **Before**: No retention policies
  - Month 1: $0.15 storage cost
  - Month 12: $1.80 accumulated storage cost
- **After**: 14-day retention
  - Month 12: $0.15/month ongoing
  - **Savings**: $1.65/month by month 12

### Medium Environment (50GB logs/month)
- **Before**: Mix of no retention and long retention
  - Annual cost: ~$180 accumulated
- **After**: Intelligent retention policies
  - Annual cost: ~$18 ongoing
  - **Savings**: $162/year (90% reduction)

## Best Practices

### 1. Start with Analysis
```bash
export DRY_RUN="true"
# Review all findings before applying changes
```

### 2. Prioritize High-Impact Changes
Focus first on:
- Log groups with no retention policy
- Large log groups with excessive retention
- High-volume Lambda function logs

### 3. Use Pattern-based Exclusions
```bash
export EXCLUDE_PATTERNS="^/aws/cloudtrail/,^/critical-app/"
# Protect specific log groups from automatic management
```

### 4. Test in Non-Production First
```bash
export EXCLUDE_PATTERNS="production,prod"
# Start with development/test log groups
```

### 5. Monitor After Changes
- Check that applications still function correctly
- Verify retention periods meet compliance requirements
- Adjust patterns based on results

## Advanced Configuration

### Environment-Specific Retention
```bash
# Production environment (longer retention)
export CRITICAL_LOG_RETENTION="90"
export DEFAULT_RETENTION_DAYS="30"

# Development environment (shorter retention)
export CRITICAL_LOG_RETENTION="14"
export DEFAULT_RETENTION_DAYS="7"
```

### Compliance-Aware Settings
```bash
# Meet 90-day compliance requirements
export CRITICAL_LOG_RETENTION="90"
export EXCLUDE_PATTERNS="audit,security,compliance"
```

### High-Volume Environment
```bash
# Aggressive retention for cost control
export DEFAULT_RETENTION_DAYS="3"
export CRITICAL_LOG_RETENTION="7"
export DELETE_EMPTY_GROUPS="true"
export EMPTY_GROUP_DAYS="7"
```

## Troubleshooting

**No log groups found**: Check AWS credentials and region configuration
**Permission denied**: Verify IAM permissions for CloudWatch Logs
**Retention policy failed**: Check log group exists and isn't locked
**Deletion failed**: Verify log group isn't referenced by other resources

## ROI Analysis

For a typical AWS environment:
- **10 log groups** with no retention = $3-15/month growing costs
- **After optimization** = $0.50-2/month ongoing costs
- **Savings**: 70-90% reduction in log storage costs
- **ROI**: Usually pays for itself within 1-2 months

Regular optimization ensures log costs stay under control as your environment grows!
