#!/usr/bin/env python3
"""
security_group_audit.py -- Audit AWS Security Groups for security and cleanup opportunities.

This script analyzes AWS Security Groups across regions to identify:
1. Unused security groups (not attached to any resources)
2. Overly permissive rules (0.0.0.0/0 access, especially SSH/RDP)
3. Security groups with suspicious or dangerous configurations
4. Opportunities for rule consolidation

While security groups don't have direct costs, maintaining good security hygiene
and cleaning up unused resources improves security posture and simplifies management.

Environment variables:
    REGIONS: Comma-separated list of AWS regions to scan.
    CHECK_UNUSED: If "true", identify unused security groups.
    CHECK_PERMISSIVE: If "true", identify overly permissive rules.
    CHECK_SUSPICIOUS_PORTS: If "true", check for unusual port combinations.
    AUTO_DELETE_UNUSED: If "true", delete unused security groups (DANGEROUS!).
    EXCLUDE_DEFAULT: If "true", exclude default security groups from analysis.
    ALERT_ON_HIGH_RISK: If "true", send alerts for high-risk findings only.
    DRY_RUN: If "true", logs actions without making changes.
    ALERT_WEBHOOK: Optional HTTP endpoint for notifications.

Usage:
    python security_group_audit.py
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import requests


def log(msg: str) -> None:
    """Prints a timestamped message to stdout."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}")


def get_regions() -> List[str]:
    """Get list of regions to scan."""
    regions_env = os.getenv("REGIONS")
    if regions_env:
        return [r.strip() for r in regions_env.split(",") if r.strip()]
    default = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    return [default]


def get_security_group_name(sg: Dict) -> str:
    """Get a friendly name for the security group."""
    name = sg.get('GroupName', '')
    if name and name != 'default':
        return name

    # Check tags for a Name tag
    tags = sg.get('Tags', [])
    for tag in tags:
        if tag['Key'].lower() == 'name':
            return tag['Value']

    return sg.get('GroupId', 'Unknown')


def is_default_security_group(sg: Dict) -> bool:
    """Check if this is a default security group."""
    return sg.get('GroupName') == 'default'


def find_unused_security_groups(ec2_client, region: str) -> List[Dict]:
    """Find security groups that are not attached to any resources."""
    try:
        log(f"Scanning for unused security groups in {region}...")

        # Get all security groups
        sg_response = ec2_client.describe_security_groups()
        all_sgs = sg_response['SecurityGroups']

        # Get security groups in use
        used_sg_ids = set()

        # Check EC2 instances
        try:
            instances_response = ec2_client.describe_instances()
            for reservation in instances_response['Reservations']:
                for instance in reservation['Instances']:
                    for sg in instance.get('SecurityGroups', []):
                        used_sg_ids.add(sg['GroupId'])
        except ClientError as e:
            log(f"Warning: Could not check EC2 instances in {region}: {e}")

        # Check ELBs (Classic Load Balancers)
        try:
            elb_client = boto3.client('elb', region_name=region)
            elb_response = elb_client.describe_load_balancers()
            for elb in elb_response['LoadBalancerDescriptions']:
                for sg_id in elb.get('SecurityGroups', []):
                    used_sg_ids.add(sg_id)
        except ClientError as e:
            log(f"Warning: Could not check classic ELBs in {region}: {e}")

        # Check ALBs/NLBs
        try:
            elbv2_client = boto3.client('elbv2', region_name=region)
            elbv2_response = elbv2_client.describe_load_balancers()
            for elb in elbv2_response['LoadBalancers']:
                for sg_id in elb.get('SecurityGroups', []):
                    used_sg_ids.add(sg_id)
        except ClientError as e:
            log(f"Warning: Could not check ALBs/NLBs in {region}: {e}")

        # Check RDS instances
        try:
            rds_client = boto3.client('rds', region_name=region)
            rds_response = rds_client.describe_db_instances()
            for db in rds_response['DBInstances']:
                for sg in db.get('VpcSecurityGroups', []):
                    used_sg_ids.add(sg['VpcSecurityGroupId'])
        except ClientError as e:
            log(f"Warning: Could not check RDS instances in {region}: {e}")

        # Check Lambda functions
        try:
            lambda_client = boto3.client('lambda', region_name=region)
            functions_response = lambda_client.list_functions()
            for function in functions_response['Functions']:
                vpc_config = function.get('VpcConfig', {})
                for sg_id in vpc_config.get('SecurityGroupIds', []):
                    used_sg_ids.add(sg_id)
        except ClientError as e:
            log(f"Warning: Could not check Lambda functions in {region}: {e}")

        # Also check if security groups reference each other
        for sg in all_sgs:
            for rule in sg.get('IpPermissions', []) + sg.get('IpPermissionsEgress', []):
                for group_pair in rule.get('UserIdGroupPairs', []):
                    referenced_sg_id = group_pair.get('GroupId')
                    if referenced_sg_id:
                        used_sg_ids.add(referenced_sg_id)

        # Find unused security groups
        unused_sgs = []
        for sg in all_sgs:
            if sg['GroupId'] not in used_sg_ids:
                unused_sgs.append({
                    **sg,
                    'Region': region,
                    'Name': get_security_group_name(sg)
                })

        log(f"Found {len(unused_sgs)} unused security group(s) in {region}")
        return unused_sgs

    except ClientError as e:
        log(f"Error finding unused security groups in {region}: {e}")
        return []


def analyze_permissive_rules(sg: Dict, region: str) -> List[Dict]:
    """Analyze security group for overly permissive rules."""
    findings = []
    sg_id = sg['GroupId']
    sg_name = get_security_group_name(sg)

    # Define risky ports
    critical_ports = {
        22: 'SSH',
        3389: 'RDP',
        1433: 'SQL Server',
        3306: 'MySQL',
        5432: 'PostgreSQL',
        6379: 'Redis',
        27017: 'MongoDB'
    }

    # Check inbound rules
    for rule in sg.get('IpPermissions', []):
        from_port = rule.get('FromPort')
        to_port = rule.get('ToPort')
        protocol = rule.get('IpProtocol', 'unknown')

        # Check for 0.0.0.0/0 access
        for ip_range in rule.get('IpRanges', []):
            cidr = ip_range.get('CidrIp')
            if cidr == '0.0.0.0/0':
                risk_level = 'HIGH'
                description = f"Open to internet (0.0.0.0/0)"

                if from_port in critical_ports:
                    risk_level = 'CRITICAL'
                    description = f"CRITICAL: {critical_ports[from_port]} open to internet"
                elif from_port == to_port and from_port:
                    description = f"Port {from_port} ({protocol}) open to internet"
                elif from_port != to_port:
                    description = f"Port range {from_port}-{to_port} ({protocol}) open to internet"

                findings.append({
                    'type': 'permissive_rule',
                    'risk_level': risk_level,
                    'sg_id': sg_id,
                    'sg_name': sg_name,
                    'region': region,
                    'description': description,
                    'from_port': from_port,
                    'to_port': to_port,
                    'protocol': protocol,
                    'source': cidr
                })

    # Check for overly broad port ranges
    for rule in sg.get('IpPermissions', []):
        from_port = rule.get('FromPort', 0)
        to_port = rule.get('ToPort', 65535)

        if to_port - from_port > 1000:  # Large port range
            findings.append({
                'type': 'broad_port_range',
                'risk_level': 'MEDIUM',
                'sg_id': sg_id,
                'sg_name': sg_name,
                'region': region,
                'description': f"Very broad port range: {from_port}-{to_port}",
                'from_port': from_port,
                'to_port': to_port
            })

    return findings


def check_suspicious_configurations(sg: Dict, region: str) -> List[Dict]:
    """Check for suspicious or unusual security group configurations."""
    findings = []
    sg_id = sg['GroupId']
    sg_name = get_security_group_name(sg)

    inbound_rules = sg.get('IpPermissions', [])
    outbound_rules = sg.get('IpPermissionsEgress', [])

    # Check for too many rules (complexity)
    total_rules = len(inbound_rules) + len(outbound_rules)
    if total_rules > 50:
        findings.append({
            'type': 'complex_sg',
            'risk_level': 'LOW',
            'sg_id': sg_id,
            'sg_name': sg_name,
            'region': region,
            'description': f"Security group has {total_rules} rules (complexity risk)",
            'rule_count': total_rules
        })

    # Check for unusual port combinations that might indicate misconfigurations
    open_ports = set()
    for rule in inbound_rules:
        from_port = rule.get('FromPort')
        to_port = rule.get('ToPort')
        if from_port == to_port and from_port:
            open_ports.add(from_port)

    # Check for risky combinations
    if 22 in open_ports and 3389 in open_ports:
        findings.append({
            'type': 'mixed_os_access',
            'risk_level': 'MEDIUM',
            'sg_id': sg_id,
            'sg_name': sg_name,
            'region': region,
            'description': "Both SSH (22) and RDP (3389) ports open (unusual for single OS)"
        })

    # Check for default egress rule modifications
    default_egress = {
        'IpProtocol': '-1',
        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
    }

    if len(outbound_rules) != 1 or not any(
        rule.get('IpProtocol') == '-1' and
        any(ip_range.get('CidrIp') == '0.0.0.0/0' for ip_range in rule.get('IpRanges', []))
        for rule in outbound_rules
    ):
        findings.append({
            'type': 'modified_egress',
            'risk_level': 'LOW',
            'sg_id': sg_id,
            'sg_name': sg_name,
            'region': region,
            'description': "Default egress rule has been modified (review needed)"
        })

    return findings


def delete_security_group(ec2_client, sg_id: str, sg_name: str, dry_run: bool) -> bool:
    """Delete an unused security group."""
    try:
        if dry_run:
            log(f"DRY RUN: Would delete security group {sg_id} ({sg_name})")
            return True

        log(f"Deleting security group {sg_id} ({sg_name})")
        ec2_client.delete_security_group(GroupId=sg_id)
        log(f"Successfully deleted security group {sg_id}")
        return True

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'InvalidGroup.NotFound':
            log(f"Security group {sg_id} was already deleted")
            return True
        elif error_code == 'DependencyViolation':
            log(f"Cannot delete {sg_id}: still has dependencies")
        else:
            log(f"Failed to delete security group {sg_id}: {e}")
        return False


def send_alert(webhook: str, audit_results: Dict) -> None:
    """Send security group audit results to webhook."""
    unused_count = len(audit_results.get('unused_sgs', []))
    findings = audit_results.get('security_findings', [])

    if not unused_count and not findings:
        return

    # Count findings by risk level
    risk_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    for finding in findings:
        risk_level = finding.get('risk_level', 'LOW')
        risk_counts[risk_level] += 1

    message_lines = [
        f"AWS Security Group Audit Report",
        f""
    ]

    if unused_count > 0:
        message_lines.append(f"Unused security groups: {unused_count}")

    if findings:
        message_lines.extend([
            f"Security findings:",
            f"  Critical: {risk_counts['CRITICAL']}",
            f"  High: {risk_counts['HIGH']}",
            f"  Medium: {risk_counts['MEDIUM']}",
            f"  Low: {risk_counts['LOW']}"
        ])

    message_lines.append("")

    # Show critical and high-risk findings
    critical_findings = [f for f in findings if f.get('risk_level') in ['CRITICAL', 'HIGH']]
    if critical_findings:
        message_lines.append("High-Priority Issues:")
        for finding in critical_findings[:10]:  # Limit to top 10
            message_lines.append(
                f"- {finding['sg_name']} ({finding['sg_id']}) in {finding['region']}: "
                f"{finding['description']}"
            )
        if len(critical_findings) > 10:
            message_lines.append(f"... and {len(critical_findings) - 10} more critical/high-risk issues")

    # Show sample unused security groups
    if unused_count > 0:
        message_lines.append("")
        message_lines.append("Sample Unused Security Groups:")
        unused_sgs = audit_results.get('unused_sgs', [])
        for sg in unused_sgs[:5]:  # Show first 5
            message_lines.append(f"- {sg['Name']} ({sg['GroupId']}) in {sg['Region']}")
        if len(unused_sgs) > 5:
            message_lines.append(f"... and {len(unused_sgs) - 5} more unused security groups")

    message_lines.extend([
        f"",
        f"Regular security group audits help maintain security posture",
        f"Review and clean up unused security groups",
        f"Avoid overly permissive rules (0.0.0.0/0 access)"
    ])

    payload = {"text": "\n".join(message_lines)}

    try:
        response = requests.post(webhook, json=payload, timeout=10)
        if response.status_code == 200:
            log(f"Alert sent successfully to webhook")
        else:
            log(f"Failed to send alert: HTTP {response.status_code}")
    except Exception as exc:
        log(f"Failed to send alert: {exc}")


def main() -> int:
    """Main function."""
    log("Starting security group audit")

    # Configuration
    regions = get_regions()
    check_unused = os.getenv("CHECK_UNUSED", "true").lower() == "true"
    check_permissive = os.getenv("CHECK_PERMISSIVE", "true").lower() == "true"
    check_suspicious = os.getenv("CHECK_SUSPICIOUS_PORTS", "true").lower() == "true"
    auto_delete_unused = os.getenv("AUTO_DELETE_UNUSED", "false").lower() == "true"
    exclude_default = os.getenv("EXCLUDE_DEFAULT", "true").lower() == "true"
    alert_on_high_risk = os.getenv("ALERT_ON_HIGH_RISK", "false").lower() == "true"
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    webhook = os.getenv("ALERT_WEBHOOK")

    log(f"Scanning regions: {', '.join(regions)}")
    log(f"Check unused: {check_unused}")
    log(f"Check permissive rules: {check_permissive}")
    log(f"Check suspicious configs: {check_suspicious}")
    log(f"Auto-delete unused: {auto_delete_unused}")
    log(f"Exclude default SGs: {exclude_default}")
    log(f"Dry run mode: {dry_run}")

    if auto_delete_unused and not dry_run:
        log("WARNING: Auto-delete of unused security groups is enabled!")

    audit_results = {
        'unused_sgs': [],
        'security_findings': [],
        'deleted_sgs': 0
    }

    try:
        for region in regions:
            log(f"Auditing security groups in region {region}")
            ec2_client = boto3.client('ec2', region_name=region)

            # Find unused security groups
            if check_unused:
                unused_sgs = find_unused_security_groups(ec2_client, region)

                if exclude_default:
                    unused_sgs = [sg for sg in unused_sgs if not is_default_security_group(sg)]

                audit_results['unused_sgs'].extend(unused_sgs)

                # Delete unused security groups if enabled
                if auto_delete_unused and unused_sgs:
                    log(f"Auto-deleting {len(unused_sgs)} unused security groups in {region}...")
                    for sg in unused_sgs:
                        if delete_security_group(ec2_client, sg['GroupId'], sg['Name'], dry_run):
                            audit_results['deleted_sgs'] += 1

            # Check for security issues
            if check_permissive or check_suspicious:
                try:
                    sg_response = ec2_client.describe_security_groups()
                    all_sgs = sg_response['SecurityGroups']

                    if exclude_default:
                        all_sgs = [sg for sg in all_sgs if not is_default_security_group(sg)]

                    for sg in all_sgs:
                        if check_permissive:
                            findings = analyze_permissive_rules(sg, region)
                            audit_results['security_findings'].extend(findings)

                        if check_suspicious:
                            findings = check_suspicious_configurations(sg, region)
                            audit_results['security_findings'].extend(findings)

                except ClientError as e:
                    log(f"Error checking security configurations in {region}: {e}")

        # Summary
        log(f"")
        log(f"=== SECURITY GROUP AUDIT SUMMARY ===")
        log(f"Unused security groups: {len(audit_results['unused_sgs'])}")
        log(f"Security findings: {len(audit_results['security_findings'])}")

        if audit_results['deleted_sgs'] > 0:
            action = "Would delete" if dry_run else "Deleted"
            log(f"{action} unused security groups: {audit_results['deleted_sgs']}")

        # Break down findings by risk level
        findings = audit_results['security_findings']
        if findings:
            risk_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
            for finding in findings:
                risk_level = finding.get('risk_level', 'LOW')
                risk_counts[risk_level] += 1

            log("Security findings by risk level:")
            for risk, count in risk_counts.items():
                if count > 0:
                    log(f"  {risk}: {count}")

        # Send alerts
        should_alert = False
        if alert_on_high_risk:
            # Only alert on high-risk findings
            high_risk_findings = [f for f in findings if f.get('risk_level') in ['CRITICAL', 'HIGH']]
            should_alert = len(high_risk_findings) > 0 or len(audit_results['unused_sgs']) > 0
        else:
            # Alert on any findings
            should_alert = len(findings) > 0 or len(audit_results['unused_sgs']) > 0

        if webhook and should_alert:
            send_alert(webhook, audit_results)
        elif webhook:
            log("No significant security issues found, skipping alert")

        return 0

    except NoCredentialsError:
        log("ERROR: AWS credentials not configured")
        return 1
    except Exception as exc:
        log(f"Security group audit failed: {exc}")
        return 1

    log("Security group audit completed")


if __name__ == "__main__":
    sys.exit(main())
