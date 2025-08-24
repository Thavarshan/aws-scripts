# Unused EBS Volume Detector

Find and manage unattached EBS volumes that continue to incur storage costs.

## Overview

The `unused_ebs_detector.py` script identifies EBS volumes that are not attached to any EC2 instances. These "orphaned" volumes continue to incur storage costs even though they're not being used. The script calculates costs by volume type, optionally creates backup snapshots, and can automatically clean up unused volumes.

## Key Benefits

- **Cost Transparency**: Calculate exact monthly costs by volume type
- **Safety Features**: Optional snapshot creation before deletion
- **Volume Type Awareness**: Different pricing for gp3, gp2, io1, etc.
- **Multi-region Discovery**: Find forgotten volumes across regions

## Cost Impact

EBS volumes cost money even when unattached:
- **gp3**: $0.08 per GB/month
- **gp2**: $0.10 per GB/month
- **io1**: $0.125 per GB/month + IOPS costs
- **st1**: $0.045 per GB/month
- **sc1**: $0.025 per GB/month

**Example**: A forgotten 30GB gp2 volume = $3/month (30% of $10 budget!)

## Features

- **Comprehensive Detection**: Find unattached volumes across all regions
- **Cost Calculation**: Precise monthly cost estimates by volume type
- **Safety Backups**: Create snapshots before deletion
- **Age-based Filtering**: Only consider volumes unused for X hours
- **Tag-based Exclusion**: Protect important volumes from cleanup
- **Detailed Reporting**: Volume type, size, cost, and age information

## Prerequisites

**AWS IAM Permissions:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeVolumes",
                "ec2:DeleteVolume",
                "ec2:CreateSnapshot",
                "ec2:CreateTags"
            ],
            "Resource": "*"
        }
    ]
}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MIN_UNUSED_HOURS` | `24` | Minimum hours unattached before cleanup |
| `EXCLUDE_TAGS` | None | Tag keys to exclude from cleanup |
| `CREATE_SNAPSHOTS` | `false` | Create backup snapshots before deletion |
| `AUTO_DELETE` | `false` | Automatically delete unused volumes |
| `COST_THRESHOLD` | `1.0` | Minimum monthly cost to trigger alerts |
| `DRY_RUN` | `false` | Test mode without making changes |

## Usage Examples

**Find unused volumes (safe analysis):**
```bash
export DRY_RUN="true"
python unused_ebs_detector.py
```

**Create snapshots before cleanup:**
```bash
export CREATE_SNAPSHOTS="true"
export DRY_RUN="true"  # Test first!
python unused_ebs_detector.py
```

**Auto-delete with safety measures:**
```bash
export MIN_UNUSED_HOURS="168"  # 1 week minimum
export CREATE_SNAPSHOTS="true"
export EXCLUDE_TAGS="DoNotDelete,Production"
export AUTO_DELETE="true"
export DRY_RUN="false"  # CAREFUL!
python unused_ebs_detector.py
```

## Example Output

```
[2024-01-15T10:30:15Z] Starting unused EBS volume detection
[2024-01-15T10:30:15Z] Minimum unused hours: 24
[2024-01-15T10:30:16Z] Scanning EBS volumes in region us-east-1...
[2024-01-15T10:30:16Z]   vol-1234567890abcdef0 (Web-Server-Root): in-use - 30 GB gp2
[2024-01-15T10:30:16Z]   vol-0987654321fedcba0 (Old-DB-Volume): UNUSED - 50 GB gp2, $5.00/month
[2024-01-15T10:30:16Z]   vol-1122334455667788 (Test-Volume): UNUSED - 20 GB gp3, $1.60/month
[2024-01-15T10:30:17Z] Creating snapshots for 2 volume(s) in us-east-1...
[2024-01-15T10:30:18Z] Created snapshot snap-abcdef1234567890 for volume vol-0987654321fedcba0
[2024-01-15T10:30:19Z] Auto-deleting 2 unused volume(s) in us-east-1...
[2024-01-15T10:30:20Z] Successfully deleted volume vol-0987654321fedcba0
[2024-01-15T10:30:21Z] Total unused volumes found: 2
[2024-01-15T10:30:21Z] Total monthly cost: $6.60
[2024-01-15T10:30:21Z] Monthly savings: $6.60
```

## Volume Type Detection

The script automatically detects and prices different volume types:

### General Purpose (Most Common)
- **gp3**: Latest generation, $0.08/GB/month
- **gp2**: Previous generation, $0.10/GB/month

### Provisioned IOPS (High Performance)
- **io1**: Legacy IOPS volumes, $0.125/GB/month + $0.065/IOPS
- **io2**: Next-gen IOPS volumes, $0.125/GB/month + variable IOPS cost

### Throughput Optimized (Big Data)
- **st1**: Frequently accessed, $0.045/GB/month
- **sc1**: Infrequently accessed, $0.025/GB/month

### Legacy
- **standard**: Magnetic volumes (rare), $0.05/GB/month

## Safety Features

### 1. Minimum Age Protection
```bash
export MIN_UNUSED_HOURS="168"  # 1 week minimum
```
Prevents deletion of recently detached volumes that might be temporarily unattached.

### 2. Tag-based Exclusion
```bash
export EXCLUDE_TAGS="DoNotDelete,Production,Backup"
```
Protects volumes with specific tags from cleanup.

### 3. Automatic Snapshots
```bash
export CREATE_SNAPSHOTS="true"
```
Creates backup snapshots before deletion for data recovery.

### 4. Dry-run Testing
```bash
export DRY_RUN="true"
```
Test all operations without making actual changes.

## Common Use Cases

### Monthly Cost Audit
```bash
# Find all unused volumes and their costs
export DRY_RUN="true"
export COST_THRESHOLD="0.50"  # Alert on $0.50+ monthly cost
python unused_ebs_detector.py
```

### Safe Cleanup with Backups
```bash
# Conservative cleanup with safety measures
export MIN_UNUSED_HOURS="336"  # 2 weeks minimum
export CREATE_SNAPSHOTS="true"
export EXCLUDE_TAGS="Production,Critical"
export AUTO_DELETE="true"
export DRY_RUN="false"
python unused_ebs_detector.py
```

### Development Environment Cleanup
```bash
# Aggressive cleanup for dev environment
export MIN_UNUSED_HOURS="24"   # 1 day minimum
export CREATE_SNAPSHOTS="false"  # Skip snapshots for dev
export AUTO_DELETE="true"
python unused_ebs_detector.py
```

## Integration with Other Scripts

### Budget Monitor Integration
When your budget hits 90%, the budget monitor can trigger this script for emergency cost reduction.

### Scheduled Cleanup
The GitHub Actions workflow runs monthly to identify cost opportunities:
- **Analysis Mode**: Monthly reports on unused volumes
- **Cleanup Mode**: Automated deletion with safety measures

## Best Practices

1. **Start with Analysis**: Always run with `DRY_RUN=true` first
2. **Use Minimum Ages**: Set appropriate `MIN_UNUSED_HOURS` for your environment
3. **Create Backups**: Use `CREATE_SNAPSHOTS=true` for important data
4. **Tag Strategy**: Use tags consistently to protect critical volumes
5. **Regular Audits**: Run monthly to catch forgotten volumes early
6. **Cost Thresholds**: Set alerts for volumes above certain monthly costs

## Troubleshooting

**No volumes found**: Check that you have unattached volumes in the scanned regions
**Permission denied**: Verify IAM permissions for EC2 volume operations
**Snapshot creation failed**: Ensure adequate permissions and available snapshot limits
**Volume deletion failed**: Check if volume is still attached or has delete protection

## Cost Recovery Examples

**Small Environment**:
- 2 forgotten 20GB gp2 volumes = $4/month saved
- 1 old 100GB st1 volume = $4.50/month saved
- **Total**: $8.50/month (85% of $10 budget recovered!)

**Development Cleanup**:
- 5 test volumes (various sizes) = $15-30/month saved
- Old database volume snapshots = $10-20/month saved
- **Total**: $25-50/month typical savings

Regular use of this script ensures you're not paying for storage you're not using!
