# AWS Scripts Collection

A collection of Python scripts for automating AWS operations, designed for cost optimization, resource management, and operational efficiency.

## Overview

This repository contains various Python scripts that help with common AWS tasks. Each script is designed to be robust, configurable, and suitable for both manual execution and automated workflows via GitHub Actions.

## Available Scripts

Our comprehensive AWS automation toolkit includes scripts across four main categories:

### High-Impact Cost Savers

#### Unused EIP Cleanup (`unused_eip_cleanup.py`)

**Impact: $3.60/month per unused EIP (36% of $10 budget!)**

Find and automatically release unused Elastic IP addresses.

- Multi-region scanning with tag-based exclusions
- Automatic release with safety checks
- Immediate cost impact for small budgets

**[Full Documentation](docs/UNUSED_EIP_CLEANUP.md)**

#### EC2 Auto-Off (`ec2_auto_off.py`)

**Impact: ~50% EC2 cost reduction with scheduled shutdowns**

Automatically stop or hibernate EC2 instances during off-hours.

- Tag-based filtering with hibernation support
- Multi-region scheduling via GitHub Actions
- Webhook notifications and dry-run testing

**[Full Documentation](docs/EC2_AUTO_OFF.md)**

#### RDS Auto-Stop (`rds_auto_stop.py`)

**Impact: ~50% RDS cost reduction (often $50-200+/month)**

Stop RDS database instances during off-hours while preserving data.

- Safety controls for Multi-AZ and read replicas
- Multiple database engine support
- Cost estimation and detailed reporting

**[Full Documentation](docs/RDS_AUTO_STOP.md)**

#### EBS Snapshot Cleanup (`ebs_snapshot_cleanup.py`)

**Impact: Up to 90% snapshot storage cost reduction**

Clean up old EBS snapshots using flexible retention policies.

- Intelligent daily/weekly/monthly retention
- Cost calculation showing monthly savings
- Tag-based exclusion for critical snapshots

**[Full Documentation](docs/EBS_SNAPSHOT_CLEANUP.md)**

### Storage & Resource Management

#### Unused EBS Volume Detector (`unused_ebs_detector.py`)

Find unattached EBS volumes that continue to incur storage costs.

- Automatic cost calculation by volume type
- Optional snapshot creation before deletion
- Cross-region detection and cleanup

**[Full Documentation](docs/UNUSED_EBS_DETECTOR.md)**

#### S3 Lifecycle Optimizer (`s3_lifecycle_optimizer.py`)

Optimize S3 storage costs through intelligent lifecycle management.

- Automatic transition to cheaper storage classes
- Incomplete multipart upload cleanup
- Intelligent Tiering recommendations

**[Full Documentation](docs/S3_LIFECYCLE_OPTIMIZER.md)**

#### CloudWatch Logs Optimizer (`cloudwatch_logs_optimizer.py`)

Manage CloudWatch log retention to control storage costs.

- Automatic retention policy setup
- Detection of unused/empty log groups
- Cost-based cleanup recommendations

**[Full Documentation](docs/CLOUDWATCH_LOGS_OPTIMIZER.md)**

### Security & Compliance

#### Security Group Audit (`security_group_audit.py`)

Audit security groups for cleanup and security issues.

- Find unused security groups across regions
- Detect overly permissive rules (0.0.0.0/0)
- Risk-based alerting and optional cleanup

**[Full Documentation](docs/SECURITY_GROUP_AUDIT.md)**

### Monitoring & Intelligence

#### Budget Monitor (`budget_monitor.py`)

**Central Command**: Monitor spending and trigger other scripts automatically.

- Real-time budget tracking with Cost Explorer API
- Automatic script triggering at 90%/100% thresholds
- Service-level cost breakdown and alerting

**[Full Documentation](docs/BUDGET_MONITOR.md)**

## Cost Impact Summary

This toolkit can provide substantial cost savings for AWS environments:

### For a $10 Monthly Budget

- **1 unused EIP** = $3.60/month (36% of budget) → **Released instantly**
- **EC2 auto-off** (12h daily) = ~50% reduction → **$15-30/month saved on small instances**
- **RDS auto-stop** (12h daily) = ~50% reduction → **$25-100/month saved per database**
- **EBS snapshots** cleanup = 70-90% reduction → **$5-50/month saved depending on retention**
- **Unused EBS volumes** = Full volume cost → **$3-15/month per 30GB volume**

### Realistic Monthly Savings Examples

- **Small Development Environment**: $50-100/month → $15-25/month (50-75% reduction)
- **Production Environment**: $200-500/month → $50-150/month (70-75% reduction)
- **Multi-region Setup**: $500-1000/month → $150-300/month (70% reduction)

### ROI for $10 Budget Users

Even **one unused EIP** recovered pays for 3.6 months of your entire budget!

## Quick Start Examples

**Highest Impact - Find Unused EIPs:**

```bash
# Find unused EIPs (safe mode)
export DRY_RUN="true"
python unused_eip_cleanup.py

# Each unused EIP = $3.60/month saved!
```

**Budget Monitoring:**

```bash
# Monitor your $10 budget
export MONTHLY_BUDGET="10.00"
export DRY_RUN="true"
python budget_monitor.py
```

**Scheduled Cost Savings:**

```bash
# Tag resources for auto-shutdown
aws ec2 create-tags --resources i-your-instance --tags Key=auto-off,Value=true
aws rds add-tags-to-resource --resource-name arn:aws:rds:region:account:db:mydb --tags Key=auto-off,Value=true

# Test the scripts
python ec2_auto_off.py
python rds_auto_stop.py
```

**Storage Cleanup:**

```bash
# Clean up old snapshots (test mode)
export DRY_RUN="true"
python ebs_snapshot_cleanup.py

# Find unused volumes
python unused_ebs_detector.py
```

## Script Integration

The scripts in this collection work together for comprehensive cost management:

### Automated Cost Control Workflow

1. **Scheduled Prevention**: `ec2_auto_off.py` runs daily to stop instances during off-hours
2. **Budget Monitoring**: `budget_monitor.py` runs every 6 hours to check spending
3. **Emergency Response**: When budget thresholds are hit, budget monitor automatically triggers EC2 auto-off
4. **Notifications**: Both scripts send alerts to keep you informed

### Example Scenario

- **Day 1-10**: Normal usage, EC2 auto-off saves ~50% on instance costs
- **Day 11**: Unexpected usage spike detected by budget monitor at 75% of monthly budget
- **Day 12**: Budget hits 90% threshold → Budget monitor automatically triggers EC2 auto-off script
- **Result**: Emergency cost-saving action prevents budget overrun

## Common Setup

### Prerequisites

1. **AWS Account** with appropriate services
2. **AWS IAM User** with necessary permissions for each script
3. **Python 3.11+** for local development
4. **GitHub repository** for automated workflows

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/aws-scripts.git
cd aws-scripts

# Install dependencies
pip install -r requirements.txt
```

### GitHub Actions Configuration

Configure repository secrets and variables for automated execution:

**Repository Secrets:**

- `AWS_ACCESS_KEY_ID`: Your AWS access key ID
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key
- `ALERT_WEBHOOK` (optional): Webhook URL for notifications

**Repository Variables:**

- `AWS_DEFAULT_REGION`: Default AWS region (e.g., `us-east-1`)
- `MONTHLY_BUDGET`: Monthly budget limit in USD (e.g., `10.00`)
- `WARNING_THRESHOLD`: Warning alert percentage (default: `75`)
- `CRITICAL_THRESHOLD`: Critical alert percentage (default: `90`)
- `ENABLE_SCRIPT_TRIGGERS`: Enable automatic cost-saving script triggers (`true`/`false`)

### Local Development

```bash
# Set up environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# Test with dry-run mode
export DRY_RUN="true"

# Run any script
python script_name.py
```

## Project Structure

```
aws-scripts/
├── README.md                           # This file - project overview
├── requirements.txt                    # Python dependencies
│
├── Cost Optimization Scripts
│   ├── budget_monitor.py               # Central budget monitoring & triggering
│   ├── ec2_auto_off.py                 # Stop/hibernate EC2 instances
│   ├── rds_auto_stop.py                # Stop RDS database instances
│   ├── unused_eip_cleanup.py           # Release unused Elastic IPs
│   ├── ebs_snapshot_cleanup.py         # Clean up old EBS snapshots
│   ├── unused_ebs_detector.py          # Find unattached EBS volumes
│   ├── s3_lifecycle_optimizer.py       # Optimize S3 storage costs
│   └── cloudwatch_logs_optimizer.py    # Manage log retention costs
│
├── Security & Compliance
│   └── security_group_audit.py         # Security group cleanup & audit
│
├── Documentation
│   ├── BUDGET_MONITOR.md               # Budget monitoring guide
│   ├── EC2_AUTO_OFF.md                 # EC2 auto-off guide
│   ├── RDS_AUTO_STOP.md                # RDS auto-stop guide
│   ├── UNUSED_EIP_CLEANUP.md           # EIP cleanup guide
│   ├── EBS_SNAPSHOT_CLEANUP.md         # Snapshot cleanup guide
│   ├── UNUSED_EBS_DETECTOR.md          # EBS volume detection guide
│   ├── S3_LIFECYCLE_OPTIMIZER.md       # S3 optimization guide
│   ├── CLOUDWATCH_LOGS_OPTIMIZER.md    # Log retention guide
│   └── SECURITY_GROUP_AUDIT.md         # Security audit guide
│
└── GitHub Actions Workflows
    ├── budget-monitor.yml             # Budget monitoring (every 6h)
    ├── ec2-auto-off.yml               # Daily EC2 shutdown (14:30 UTC)
    ├── rds-auto-stop.yml              # Daily RDS shutdown (14:30 UTC)
    ├── unused-eip-cleanup.yml         # Weekly EIP cleanup (Sundays)
    ├── ebs-snapshot-cleanup.yml       # Weekly snapshot cleanup (Saturdays)
    ├── unused-ebs-detector.yml        # Monthly EBS volume audit (1st of month)
    ├── s3-lifecycle-optimizer.yml     # Monthly S3 optimization (15th)
    ├── cloudwatch-logs-optimizer.yml  # Monthly log retention (10th)
    └── security-group-audit.yml       # Weekly security audit (Mondays)
```

## Adding New Scripts

When adding new AWS scripts to this collection:

1. **Create the Python script** with proper error handling and logging
2. **Add environment variable configuration** for flexibility
3. **Include dry-run mode** for safe testing
4. **Create dedicated documentation** in the `docs/` directory (e.g., `docs/SCRIPT_NAME.md`)
5. **Add GitHub Actions workflow** if needed for automation
6. **Update this README** with script information
7. **Update `requirements.txt`** if new dependencies are needed

## Security Best Practices

- **Never commit AWS credentials** to the repository
- **Use repository secrets** for sensitive information
- **Follow principle of least privilege** for IAM permissions:
  - **EC2**: `ec2:DescribeInstances`, `ec2:StopInstances`, `ec2:DescribeAddresses`, `ec2:ReleaseAddress`, `ec2:DescribeVolumes`, `ec2:DeleteVolume`, `ec2:DescribeSnapshots`, `ec2:DeleteSnapshot`, `ec2:CreateSnapshot`, `ec2:DescribeSecurityGroups`, `ec2:DeleteSecurityGroup`
  - **RDS**: `rds:DescribeDBInstances`, `rds:StopDBInstance`, `rds:ListTagsForResource`
  - **S3**: `s3:ListBucket`, `s3:GetBucketLifecycleConfiguration`, `s3:PutBucketLifecycleConfiguration`, `s3:ListMultipartUploadParts`, `s3:AbortMultipartUpload`
  - **CloudWatch**: `logs:DescribeLogGroups`, `logs:PutRetentionPolicy`, `logs:DeleteLogGroup`, `cloudwatch:GetMetricStatistics`
  - **Cost Explorer**: `ce:GetCostAndUsage`
- **Regularly rotate access keys**
- **Use AWS IAM roles** when running on AWS infrastructure
- **Enable CloudTrail** for audit logging
- **Test scripts in non-production environments** first

## Common Environment Variables

Most scripts in this collection use these standard environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_ACCESS_KEY_ID` | AWS access key ID | Required |
| `AWS_SECRET_ACCESS_KEY` | AWS secret access key | Required |
| `AWS_DEFAULT_REGION` | Default AWS region | `us-east-1` |
| `DRY_RUN` | Test mode without making changes | `false` |
| `ALERT_WEBHOOK` | Webhook URL for notifications | None |

## Contributing

When contributing new scripts:

1. Follow existing code patterns and structure
2. Include comprehensive error handling
3. Add proper logging with timestamps
4. Support dry-run mode
5. Include thorough documentation
6. Test in multiple scenarios
7. Follow Python best practices (PEP 8)

## License

This collection is provided as-is for educational and operational purposes. Use at your own risk and ensure compliance with your organization's policies.
