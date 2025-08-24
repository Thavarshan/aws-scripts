# AWS Scripts Collection

A collection of Python scripts for automating AWS operations, designed for cost optimization, resource management, and operational efficiency.

## Overview

This repository contains various Python scripts that help with common AWS tasks. Each script is designed to be robust, configurable, and suitable for both manual execution and automated workflows via GitHub Actions.

## Available Scripts

### EC2 Auto-Off (`ec2_auto_off.py`)

Automatically stop or hibernate EC2 instances based on tags to reduce costs during off-hours.

**Key Features:**

- Tag-based instance filtering
- Multi-region support
- Hibernation with fallback to stop
- Dry-run mode for testing
- Webhook notifications (Slack/Discord)
- Scheduled execution via GitHub Actions

**[Full Documentation](docs/EC2_AUTO_OFF.md)**

**Quick Usage:**

```bash
# Tag instances for auto-off
aws ec2 create-tags --resources i-your-instance --tags Key=auto-off,Value=true

# Run locally
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
python ec2_auto_off.py
```

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
├── ec2_auto_off.py                     # EC2 auto-off script
├── docs/                               # Documentation directory
│   └── EC2_AUTO_OFF.md                # EC2 script documentation
└── .github/workflows/
    └── ec2-auto-off.yml               # GitHub Actions workflow
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
- **Follow principle of least privilege** for IAM permissions
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
