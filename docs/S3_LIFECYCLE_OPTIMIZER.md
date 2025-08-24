# S3 Lifecycle Optimizer

Optimize S3 storage costs through intelligent lifecycle management and storage class transitions.

## Overview

The `s3_lifecycle_optimizer.py` script analyzes S3 buckets to identify cost optimization opportunities through lifecycle policies, storage class transitions, and cleanup operations. S3 storage costs can be significantly reduced by moving data to appropriate storage classes based on access patterns.

## Cost Impact

S3 storage costs vary dramatically by storage class:

| Storage Class | Cost per GB/month | Use Case |
|---------------|-------------------|-----------|
| **Standard** | $0.023 | Frequently accessed |
| **Standard-IA** | $0.0125 | Infrequently accessed |
| **One Zone-IA** | $0.01 | Infrequent, non-critical |
| **Glacier Instant** | $0.004 | Archive with instant retrieval |
| **Glacier Flexible** | $0.0036 | Archive with flexible retrieval |
| **Deep Archive** | $0.00099 | Long-term archive |

**Example**: 100GB in Standard ($2.30/month) → Glacier ($0.36/month) = **$1.94/month saved**

## Key Features

- **Lifecycle Policy Management**: Automatic transition rule creation
- **Intelligent Tiering**: Enable S3's ML-based cost optimization
- **Multipart Upload Cleanup**: Remove incomplete uploads that cost money
- **Cost Analysis**: Calculate potential savings from optimizations
- **Bucket-level Control**: Target specific buckets or scan all
- **Safe Operations**: Dry-run mode for testing policies

## Prerequisites

**AWS IAM Permissions:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:GetBucketLocation",
                "s3:GetBucketLifecycleConfiguration",
                "s3:PutBucketLifecycleConfiguration",
                "s3:ListMultipartUploadParts",
                "s3:AbortMultipartUpload",
                "s3:GetBucketIntelligentTieringConfiguration",
                "s3:PutBucketIntelligentTieringConfiguration",
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
| `BUCKETS` | All buckets | Comma-separated bucket names to analyze |
| `ENABLE_LIFECYCLE_POLICIES` | `false` | Create/update lifecycle policies |
| `TRANSITION_TO_IA_DAYS` | `30` | Days before transitioning to IA |
| `TRANSITION_TO_GLACIER_DAYS` | `90` | Days before transitioning to Glacier |
| `ENABLE_INTELLIGENT_TIERING` | `false` | Enable S3 Intelligent-Tiering |
| `CLEAN_INCOMPLETE_UPLOADS` | `false` | Clean up incomplete uploads |
| `INCOMPLETE_UPLOAD_DAYS` | `7` | Age for cleaning incomplete uploads |
| `DRY_RUN` | `false` | Test mode without making changes |

## Usage Examples

**Analyze all buckets (safe mode):**
```bash
export DRY_RUN="true"
python s3_lifecycle_optimizer.py
```

**Target specific buckets:**
```bash
export BUCKETS="my-data-bucket,my-backup-bucket"
export DRY_RUN="true"
python s3_lifecycle_optimizer.py
```

**Enable automatic optimizations:**
```bash
export ENABLE_LIFECYCLE_POLICIES="true"
export ENABLE_INTELLIGENT_TIERING="true"
export CLEAN_INCOMPLETE_UPLOADS="true"
export DRY_RUN="false"  # Make actual changes
python s3_lifecycle_optimizer.py
```

**Custom transition periods:**
```bash
export TRANSITION_TO_IA_DAYS="7"      # Quick transition to IA
export TRANSITION_TO_GLACIER_DAYS="30" # Quick archival
export ENABLE_LIFECYCLE_POLICIES="true"
python s3_lifecycle_optimizer.py
```

## Example Output

```
[2024-01-15T11:00:15Z] Starting S3 lifecycle optimization
[2024-01-15T11:00:16Z] Analyzing bucket: my-data-bucket
[2024-01-15T11:00:17Z]   Size: 250.5 GB
[2024-01-15T11:00:17Z]   Current cost: $5.76/month
[2024-01-15T11:00:17Z]   Potential savings: $3.45/month
[2024-01-15T11:00:18Z] DRY RUN: Would apply lifecycle policy to bucket my-data-bucket
[2024-01-15T11:00:18Z] DRY RUN: Would enable Intelligent-Tiering for bucket my-backup-bucket
[2024-01-15T11:00:19Z] DRY RUN: Would clean up 5 incomplete uploads in my-logs-bucket

=== S3 LIFECYCLE OPTIMIZATION SUMMARY ===
Total buckets analyzed: 3
Total size: 780.2 GB
Current monthly cost: $17.94
Potential monthly savings: $10.80 (60.2% reduction)
```

## Optimization Strategies

### 1. Lifecycle Policies

**Standard → Standard-IA → Glacier**
```bash
export TRANSITION_TO_IA_DAYS="30"
export TRANSITION_TO_GLACIER_DAYS="90"
```

**Aggressive Cost Savings**
```bash
export TRANSITION_TO_IA_DAYS="7"
export TRANSITION_TO_GLACIER_DAYS="30"
```

**Conservative Approach**
```bash
export TRANSITION_TO_IA_DAYS="90"
export TRANSITION_TO_GLACIER_DAYS="365"
```

### 2. Intelligent Tiering

Best for unpredictable access patterns:
```bash
export ENABLE_INTELLIGENT_TIERING="true"
```

S3 automatically moves objects between:
- Frequent Access tier (Standard pricing)
- Infrequent Access tier (Standard-IA pricing)
- Archive tiers (Glacier pricing)

### 3. Incomplete Upload Cleanup

Remove abandoned multipart uploads:
```bash
export CLEAN_INCOMPLETE_UPLOADS="true"
export INCOMPLETE_UPLOAD_DAYS="7"
```

These uploads consume storage space and cost money despite being incomplete.

## Lifecycle Policy Examples

### Data Lake Pattern
```yaml
# Applied automatically by the script
Rules:
  - ID: OptimizeStorageCosts
    Status: Enabled
    Transitions:
      - Days: 30
        StorageClass: STANDARD_IA
      - Days: 90
        StorageClass: GLACIER
  - ID: CleanupIncompleteUploads
    Status: Enabled
    AbortIncompleteMultipartUpload:
      DaysAfterInitiation: 7
```

### Backup/Archive Pattern
```bash
# Quick transition for backup data
export TRANSITION_TO_IA_DAYS="1"
export TRANSITION_TO_GLACIER_DAYS="7"
```

### Log Data Pattern
```bash
# Logs accessed less frequently
export TRANSITION_TO_IA_DAYS="14"
export TRANSITION_TO_GLACIER_DAYS="60"
```

## Cost Calculation Logic

The script estimates savings based on typical data distribution:
- **50%** remains in Standard storage
- **30%** transitions to Standard-IA
- **20%** transitions to Glacier

**Real Example:**
- **100GB bucket** currently: $2.30/month
- **After optimization**: $1.38/month (50% × $0.023) + (30% × $0.0125) + (20% × $0.0036)
- **Savings**: $0.92/month (40% reduction)

## Integration Features

### Budget Monitor Integration
When spending hits thresholds, budget monitor can trigger S3 optimization as a cost-saving measure.

### Webhook Notifications
Detailed reports showing:
- Buckets analyzed and their sizes
- Potential monthly savings
- Actions taken (policies applied, tiering enabled)
- Sample of optimization opportunities

### Scheduling
Monthly GitHub Actions workflow reviews and optimizes:
- **Analysis Mode**: Generate cost optimization reports
- **Optimization Mode**: Apply lifecycle policies automatically

## Best Practices

### 1. Start with Analysis
```bash
export DRY_RUN="true"
# Review reports before enabling optimizations
```

### 2. Test on Non-Critical Buckets
```bash
export BUCKETS="test-bucket,dev-bucket"
export ENABLE_LIFECYCLE_POLICIES="true"
```

### 3. Consider Access Patterns
- **Frequently accessed data**: Keep in Standard
- **Backup/Archive data**: Quick transition to Glacier
- **Log data**: Moderate transition periods
- **Unknown patterns**: Use Intelligent Tiering

### 4. Monitor Retrieval Costs
- Standard-IA: $0.01 per GB retrieved
- Glacier: $0.01 per GB + retrieval time
- Deep Archive: $0.02 per GB + 12-hour retrieval

### 5. Regular Optimization
Run monthly to:
- Apply policies to new buckets
- Clean up incomplete uploads
- Identify new cost opportunities

## Common Savings Scenarios

### Small Environment (10GB total)
- **Before**: $0.23/month
- **After**: $0.14/month
- **Savings**: $0.09/month

### Medium Environment (1TB total)
- **Before**: $23.00/month
- **After**: $8.50/month
- **Savings**: $14.50/month (63% reduction)

### Large Environment (10TB total)
- **Before**: $230.00/month
- **After**: $85.00/month
- **Savings**: $145.00/month (63% reduction)

## Troubleshooting

**No buckets found**: Check AWS credentials and bucket permissions
**Lifecycle policy failed**: Verify bucket permissions and policy syntax
**CloudWatch metrics missing**: S3 metrics may take 24-48 hours to appear
**Intelligent Tiering failed**: Check bucket region and service availability

## Advanced Configuration

### Bucket-Specific Policies
```bash
# Different buckets, different strategies
export BUCKETS="logs-bucket"
export TRANSITION_TO_IA_DAYS="7"
export TRANSITION_TO_GLACIER_DAYS="14"
```

### Archive-Heavy Workload
```bash
export TRANSITION_TO_IA_DAYS="1"
export TRANSITION_TO_GLACIER_DAYS="1"
# Good for backup/archive data
```

### Real-Time Data
```bash
export TRANSITION_TO_IA_DAYS="90"
export TRANSITION_TO_GLACIER_DAYS="365"
# Conservative for frequently accessed data
```

This script can provide substantial S3 cost reductions with minimal operational impact!
