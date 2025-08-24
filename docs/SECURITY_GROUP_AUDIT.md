# Security Group Audit

Audit AWS Security Groups for security issues and cleanup opportunities across your AWS environment.

## Overview

The `security_group_audit.py` script performs comprehensive security group audits to identify unused security groups, overly permissive rules, and potential security risks. While security groups don't directly cost money, maintaining good security hygiene and cleaning up unused resources improves security posture and simplifies management.

## Key Security Benefits

- **Reduce Attack Surface**: Remove unused security groups
- **Identify Risks**: Find overly permissive rules (0.0.0.0/0 access)
- **Security Hygiene**: Regular cleanup prevents configuration drift
- **Compliance**: Meet security audit requirements
- **Management**: Simplify security group management

## Features

- **Unused Security Group Detection**: Find security groups not attached to resources
- **Permissive Rule Analysis**: Identify dangerous 0.0.0.0/0 access patterns
- **Critical Port Monitoring**: Special attention to SSH, RDP, database ports
- **Comprehensive Resource Checking**: Scans EC2, ELB, RDS, Lambda for usage
- **Risk-based Alerting**: Prioritize findings by security impact
- **Safe Cleanup**: Optional automatic deletion of unused groups

## Prerequisites

**AWS IAM Permissions:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeInstances",
                "ec2:DeleteSecurityGroup",
                "elasticloadbalancing:DescribeLoadBalancers",
                "rds:DescribeDBInstances",
                "lambda:ListFunctions"
            ],
            "Resource": "*"
        }
    ]
}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_UNUSED` | `true` | Find unused security groups |
| `CHECK_PERMISSIVE` | `true` | Check for overly permissive rules |
| `CHECK_SUSPICIOUS_PORTS` | `true` | Check for unusual configurations |
| `AUTO_DELETE_UNUSED` | `false` | Automatically delete unused groups |
| `EXCLUDE_DEFAULT` | `true` | Exclude default security groups |
| `ALERT_ON_HIGH_RISK` | `false` | Only alert on high-risk findings |
| `DRY_RUN` | `false` | Test mode without making changes |

## Usage Examples

**Full security audit (safe mode):**
```bash
export DRY_RUN="true"
python security_group_audit.py
```

**Focus on critical security issues:**
```bash
export CHECK_PERMISSIVE="true"
export ALERT_ON_HIGH_RISK="true"
python security_group_audit.py
```

**Clean up unused security groups:**
```bash
export AUTO_DELETE_UNUSED="true"
export DRY_RUN="true"  # Test first!
python security_group_audit.py
```

**Comprehensive audit with cleanup:**
```bash
export CHECK_UNUSED="true"
export CHECK_PERMISSIVE="true"
export CHECK_SUSPICIOUS_PORTS="true"
export AUTO_DELETE_UNUSED="true"
export DRY_RUN="false"  # Make changes
python security_group_audit.py
```

## Example Output

```
[2024-01-15T07:30:15Z] Starting security group audit
[2024-01-15T07:30:15Z] Scanning regions: us-east-1, us-west-2
[2024-01-15T07:30:16Z] Auditing security groups in region us-east-1

Unused Security Groups:
[2024-01-15T07:30:17Z] Found 3 unused security group(s) in us-east-1
[2024-01-15T07:30:17Z]   sg-1234567890abcdef0 (old-web-sg): Unused security group
[2024-01-15T07:30:17Z]   sg-0987654321fedcba0 (test-sg): Unused security group

Security Issues Found:
[2024-01-15T07:30:18Z] CRITICAL: SSH open to internet in sg-1122334455667788 (web-servers)
[2024-01-15T07:30:18Z] HIGH: Database port 3306 open to internet in sg-2233445566778899 (db-tier)
[2024-01-15T07:30:18Z] MEDIUM: Very broad port range: 1-65535 in sg-3344556677889900 (legacy-app)

Cleanup Actions:
[2024-01-15T07:30:19Z] Auto-deleting 2 unused security groups in us-east-1...
[2024-01-15T07:30:20Z] Successfully deleted sg-1234567890abcdef0
[2024-01-15T07:30:20Z] Successfully deleted sg-0987654321fedcba0

=== SECURITY GROUP AUDIT SUMMARY ===
Unused security groups: 5
Security findings: 12
  Critical: 2
  High: 4
  Medium: 3
  Low: 3
Deleted unused security groups: 5
```

## Risk Level Classification

### Critical Risk
- **SSH (port 22) open to 0.0.0.0/0**: Direct server access from internet
- **RDP (port 3389) open to 0.0.0.0/0**: Windows remote access from internet
- **Database ports open to 0.0.0.0/0**: Direct database access (MySQL, PostgreSQL, etc.)

### High Risk
- **Any port open to 0.0.0.0/0**: Broad internet access
- **Suspicious port combinations**: Both SSH and RDP (unusual for single OS)

### Medium Risk
- **Very broad port ranges**: Large ranges like 1-65535
- **Excessive rule complexity**: Security groups with 50+ rules

### Low Risk
- **Unused security groups**: Not attached to resources
- **Modified egress rules**: Non-default outbound rules

## Comprehensive Resource Detection

The script checks security group usage across multiple AWS services:

### EC2 Instances
- Primary and secondary network interfaces
- All security groups attached to running instances

### Load Balancers
- Classic ELBs (Elastic Load Balancers)
- ALBs/NLBs (Application/Network Load Balancers)
- Security groups assigned to load balancers

### RDS Instances
- Database instances and clusters
- VPC security groups for RDS

### Lambda Functions
- VPC-enabled Lambda functions
- Security groups in VPC configuration

### Security Group References
- Security groups that reference other security groups
- Self-referencing security group rules

## Critical Port Monitoring

The script pays special attention to commonly attacked ports:

| Port | Service | Risk Level |
|------|---------|------------|
| 22 | SSH | Critical |
| 3389 | RDP | Critical |
| 1433 | SQL Server | Critical |
| 3306 | MySQL | Critical |
| 5432 | PostgreSQL | Critical |
| 6379 | Redis | Critical |
| 27017 | MongoDB | Critical |

## Webhook Notifications

Security audit reports include:

```json
{
  "text": "AWS Security Group Audit Report\n\nUnused security groups: 5\nSecurity findings:\n  Critical: 2\n  High: 4\n\nHigh-Priority Issues:\n- web-sg (sg-123) in us-east-1: CRITICAL: SSH open to internet\n- db-sg (sg-456) in us-east-1: Database port 3306 open to internet\n\nRegular audits maintain security posture\nAvoid overly permissive rules"
}
```

## Automated Cleanup Features

### Safe Unused Group Removal
```bash
export AUTO_DELETE_UNUSED="true"
export EXCLUDE_DEFAULT="true"  # Protect default groups
```

**Safety Checks:**
- Won't delete groups attached to resources
- Won't delete groups referenced by other groups
- Won't delete default security groups
- Comprehensive dependency checking

### Dry-run Testing
```bash
export DRY_RUN="true"
export AUTO_DELETE_UNUSED="true"
# See what would be deleted without making changes
```

## Integration Features

### Budget Monitor Integration
While security groups don't cost money directly, unused resources:
- Increase management complexity
- Create potential security risks
- Contribute to configuration drift

### Scheduled Security Audits
Weekly GitHub Actions workflow provides:
- **Regular Monitoring**: Continuous security posture assessment
- **Trend Analysis**: Track security hygiene over time
- **Automated Cleanup**: Optional unused group removal

## Best Practices

### 1. Regular Audits
```bash
# Weekly security reviews
export CHECK_PERMISSIVE="true"
export ALERT_ON_HIGH_RISK="true"
```

### 2. Progressive Cleanup
```bash
# Start with analysis only
export DRY_RUN="true"
export AUTO_DELETE_UNUSED="true"

# Then enable cleanup after review
export DRY_RUN="false"
```

### 3. Focus on High-Risk Issues First
```bash
export ALERT_ON_HIGH_RISK="true"
# Prioritize critical and high-risk findings
```

### 4. Protect Critical Groups
```bash
export EXCLUDE_DEFAULT="true"
# Use tags to protect important security groups
```

### 5. Multi-Region Coverage
```bash
export REGIONS="us-east-1,us-west-2,eu-west-1"
# Ensure comprehensive coverage
```

## Common Security Issues Found

### 1. SSH/RDP Open to Internet
**Risk**: Direct server access from anywhere
**Fix**: Restrict to specific IP ranges or VPN endpoints
```bash
# Instead of 0.0.0.0/0, use:
# - Corporate IP ranges: 203.0.113.0/24
# - VPN endpoints: 198.51.100.0/24
```

### 2. Database Ports Exposed
**Risk**: Direct database access bypass application security
**Fix**: Only allow access from application security groups
```bash
# Remove 0.0.0.0/0 rules for ports 3306, 5432, 1433, etc.
# Use security group references instead
```

### 3. Overly Broad Rules
**Risk**: More access than necessary
**Fix**: Use specific ports and sources
```bash
# Instead of: 0-65535 open to 0.0.0.0/0
# Use: specific ports (80, 443) from specific sources
```

### 4. Unused Security Groups
**Risk**: Configuration complexity, potential misuse
**Fix**: Regular cleanup of unused groups

## Compliance Integration

### SOC 2 / ISO 27001
- Regular security group audits demonstrate access control monitoring
- Automated cleanup shows proactive security management
- Risk-based alerting provides audit trail

### PCI DSS
- Database port monitoring helps protect cardholder data
- Network access controls documentation
- Regular security reviews requirement

### GDPR / Privacy
- Access control monitoring for personal data systems
- Regular security assessments
- Incident response preparation

## Advanced Usage

### Custom Risk Thresholds
```bash
export ALERT_ON_HIGH_RISK="true"  # Only critical/high alerts
export CHECK_SUSPICIOUS_PORTS="false"  # Skip low-priority checks
```

### Environment-Specific Audits
```bash
# Production focus (stricter)
export CHECK_PERMISSIVE="true"
export AUTO_DELETE_UNUSED="false"  # Manual review

# Development cleanup (more aggressive)
export AUTO_DELETE_UNUSED="true"
export CHECK_SUSPICIOUS_PORTS="false"
```

### Integration with SIEM
Export findings to security tools:
```bash
# Use webhook alerts to feed SIEM systems
export ALERT_WEBHOOK="https://siem.company.com/aws-security-webhook"
```

## ROI for Security

While security groups don't have direct costs:
- **Reduced incident response time**: Faster identification of security issues
- **Compliance automation**: Automated audit trail generation
- **Risk mitigation**: Proactive identification of security gaps
- **Management efficiency**: Cleaner, more manageable security configuration

Regular security group audits are essential for maintaining secure AWS environments!
