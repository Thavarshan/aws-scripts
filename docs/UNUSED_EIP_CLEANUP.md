# Unused EIP Cleanup Script

Find and optionally release unused Elastic IP addresses to eliminate unnecessary costs.

## Overview

The `unused_eip_cleanup.py` script scans AWS regions for Elastic IP addresses that are not associated with any running instances or network interfaces. Each unused EIP costs $0.005 per hour ($3.60 per month), which can quickly consume a significant portion of a small budget.

## Key Impact

- **High Cost Impact**: Each unused EIP = $3.60/month (36% of a $10 budget!)
- **Immediate Savings**: Released EIPs provide instant cost reduction
- **Safety Features**: Tag-based exclusion and dry-run mode for testing

## Features

- **Multi-region scanning** for comprehensive EIP audit
- **Tag-based exclusion** to protect important EIPs
- **Automatic release** with safety checks
- **Cost calculation** showing monthly savings potential
- **Detailed reporting** with EIP usage status

## Prerequisites

**AWS IAM Permissions:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeAddresses",
                "ec2:ReleaseAddress"
            ],
            "Resource": "*"
        }
    ]
}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REGIONS` | `AWS_DEFAULT_REGION` | Comma-separated regions to scan |
| `AUTO_RELEASE` | `false` | Automatically release unused EIPs |
| `EXCLUDE_TAGS` | None | Tag keys to exclude from cleanup |
| `MIN_UNUSED_HOURS` | `1` | Minimum unused time before cleanup |
| `COST_THRESHOLD` | `1.0` | Minimum monthly cost to trigger alerts |
| `DRY_RUN` | `false` | Test mode without making changes |
| `ALERT_WEBHOOK` | None | Webhook URL for notifications |

## Usage Examples

**Find unused EIPs (safe mode):**
```bash
export DRY_RUN="true"
python unused_eip_cleanup.py
```

**Auto-release unused EIPs:**
```bash
export AUTO_RELEASE="true"
export DRY_RUN="false"  # CAREFUL!
python unused_eip_cleanup.py
```

**Exclude tagged EIPs:**
```bash
export EXCLUDE_TAGS="DoNotDelete,Production"
python unused_eip_cleanup.py
```

## Example Output

```
[2024-01-15T10:30:15Z] Starting unused EIP cleanup scan
[2024-01-15T10:30:15Z] Scanning regions: us-east-1, us-west-2
[2024-01-15T10:30:16Z] Found 3 Elastic IP(s) in us-east-1
[2024-01-15T10:30:16Z]   54.123.456.789 (Web-Server-EIP): In use (associated with i-1234567890abcdef0)
[2024-01-15T10:30:16Z]   34.567.890.123 (Unused-EIP): UNUSED - costing $3.60/month
[2024-01-15T10:30:16Z]   76.890.123.456 (Test-EIP): UNUSED - costing $3.60/month
[2024-01-15T10:30:17Z] Auto-releasing 2 unused EIP(s) in us-east-1...
[2024-01-15T10:30:17Z] Successfully released EIP 34.567.890.123 - saving $3.60/month
[2024-01-15T10:30:18Z] Successfully released EIP 76.890.123.456 - saving $3.60/month
[2024-01-15T10:30:18Z] Total monthly cost: $7.20
[2024-01-15T10:30:18Z] Monthly savings: $7.20
```

## Safety Recommendations

1. **Always test first**: Run with `DRY_RUN=true` before auto-release
2. **Tag protection**: Use `EXCLUDE_TAGS` for critical EIPs
3. **Review reports**: Check the output before enabling auto-release
4. **Monitor alerts**: Configure webhook notifications for visibility

## Integration with Budget Monitor

The budget monitor can automatically trigger this script when spending thresholds are exceeded, providing emergency cost control when needed.

## Return Codes

- `0`: Success
- `1`: Found unused EIPs (can trigger alerts/automation)

This makes the script suitable for monitoring systems that can take action based on exit codes.
