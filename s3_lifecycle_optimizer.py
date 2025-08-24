#!/usr/bin/env python3
"""
s3_lifecycle_optimizer.py -- Optimize S3 storage costs through lifecycle management.

This script analyzes S3 buckets and helps optimize storage costs through:
1. Setting up lifecycle policies to transition objects to cheaper storage classes
2. Identifying and cleaning up incomplete multipart uploads
3. Detecting opportunities for Intelligent Tiering
4. Reporting potential cost savings

S3 Storage Classes (approximate costs per GB/month):
- Standard: $0.023
- Standard-IA: $0.0125
- One Zone-IA: $0.01
- Glacier Instant Retrieval: $0.004
- Glacier Flexible Retrieval: $0.0036
- Glacier Deep Archive: $0.00099

Environment variables:
    BUCKETS: Comma-separated list of bucket names to analyze (default: all buckets).
    ENABLE_LIFECYCLE_POLICIES: If "true", create/update lifecycle policies.
    TRANSITION_TO_IA_DAYS: Days after which to transition to Standard-IA (default: 30).
    TRANSITION_TO_GLACIER_DAYS: Days after which to transition to Glacier (default: 90).
    ENABLE_INTELLIGENT_TIERING: If "true", enable S3 Intelligent-Tiering.
    CLEAN_INCOMPLETE_UPLOADS: If "true", clean up incomplete multipart uploads.
    INCOMPLETE_UPLOAD_DAYS: Age in days for cleaning incomplete uploads (default: 7).
    DRY_RUN: If "true", logs actions without making changes.
    ALERT_WEBHOOK: Optional HTTP endpoint for notifications.

Usage:
    python s3_lifecycle_optimizer.py
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import requests


def log(msg: str) -> None:
    """Prints a timestamped message to stdout."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}")


def get_bucket_list(s3_client) -> List[str]:
    """Get list of buckets to analyze."""
    buckets_env = os.getenv("BUCKETS")
    if buckets_env:
        return [b.strip() for b in buckets_env.split(",") if b.strip()]

    # Get all buckets if none specified
    try:
        response = s3_client.list_buckets()
        return [bucket['Name'] for bucket in response['Buckets']]
    except ClientError as e:
        log(f"Error listing buckets: {e}")
        return []


def analyze_bucket_storage(s3_client, cloudwatch_client, bucket_name: str) -> Dict:
    """Analyze storage usage and costs for a bucket."""
    try:
        log(f"Analyzing bucket: {bucket_name}")

        # Get bucket size from CloudWatch metrics (more efficient than listing all objects)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=2)  # Get recent metrics

        # Get bucket size metrics
        size_response = cloudwatch_client.get_metric_statistics(
            Namespace='AWS/S3',
            MetricName='BucketSizeBytes',
            Dimensions=[
                {'Name': 'BucketName', 'Value': bucket_name},
                {'Name': 'StorageType', 'Value': 'StandardStorage'}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,  # Daily
            Statistics=['Average']
        )

        # Get object count metrics
        count_response = cloudwatch_client.get_metric_statistics(
            Namespace='AWS/S3',
            MetricName='NumberOfObjects',
            Dimensions=[
                {'Name': 'BucketName', 'Value': bucket_name},
                {'Name': 'StorageType', 'Value': 'AllStorageTypes'}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=['Average']
        )

        bucket_size_bytes = 0
        object_count = 0

        if size_response['Datapoints']:
            bucket_size_bytes = size_response['Datapoints'][-1]['Average']

        if count_response['Datapoints']:
            object_count = int(count_response['Datapoints'][-1]['Average'])

        bucket_size_gb = bucket_size_bytes / (1024**3)
        monthly_cost_standard = bucket_size_gb * 0.023  # Standard storage cost

        return {
            'bucket_name': bucket_name,
            'size_bytes': bucket_size_bytes,
            'size_gb': bucket_size_gb,
            'object_count': object_count,
            'monthly_cost_standard': monthly_cost_standard
        }

    except ClientError as e:
        log(f"Error analyzing bucket {bucket_name}: {e}")
        return {
            'bucket_name': bucket_name,
            'size_bytes': 0,
            'size_gb': 0,
            'object_count': 0,
            'monthly_cost_standard': 0,
            'error': str(e)
        }


def get_current_lifecycle_policy(s3_client, bucket_name: str) -> Optional[Dict]:
    """Get current lifecycle policy for a bucket."""
    try:
        response = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
        return response
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchLifecycleConfiguration':
            return None
        log(f"Error getting lifecycle policy for {bucket_name}: {e}")
        return None


def create_lifecycle_policy(transition_to_ia_days: int, transition_to_glacier_days: int,
                          incomplete_upload_days: int) -> Dict:
    """Create a lifecycle policy configuration."""
    rules = [
        {
            'ID': 'OptimizeStorageCosts',
            'Status': 'Enabled',
            'Filter': {'Prefix': ''},  # Apply to all objects
            'Transitions': [
                {
                    'Days': transition_to_ia_days,
                    'StorageClass': 'STANDARD_IA'
                },
                {
                    'Days': transition_to_glacier_days,
                    'StorageClass': 'GLACIER'
                }
            ]
        }
    ]

    # Add incomplete multipart upload cleanup
    if incomplete_upload_days > 0:
        rules.append({
            'ID': 'CleanupIncompleteUploads',
            'Status': 'Enabled',
            'Filter': {'Prefix': ''},
            'AbortIncompleteMultipartUpload': {
                'DaysAfterInitiation': incomplete_upload_days
            }
        })

    return {'Rules': rules}


def apply_lifecycle_policy(s3_client, bucket_name: str, policy: Dict, dry_run: bool) -> bool:
    """Apply lifecycle policy to a bucket."""
    try:
        if dry_run:
            log(f"DRY RUN: Would apply lifecycle policy to bucket {bucket_name}")
            log(f"Policy: {json.dumps(policy, indent=2)}")
            return True

        log(f"Applying lifecycle policy to bucket {bucket_name}")
        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration=policy
        )
        log(f"Successfully applied lifecycle policy to {bucket_name}")
        return True

    except ClientError as e:
        log(f"Failed to apply lifecycle policy to {bucket_name}: {e}")
        return False


def enable_intelligent_tiering(s3_client, bucket_name: str, dry_run: bool) -> bool:
    """Enable S3 Intelligent-Tiering for a bucket."""
    try:
        if dry_run:
            log(f"DRY RUN: Would enable Intelligent-Tiering for bucket {bucket_name}")
            return True

        log(f"Enabling Intelligent-Tiering for bucket {bucket_name}")

        # Create intelligent tiering configuration
        config = {
            'Id': 'EntireBucket',
            'Status': 'Enabled',
            'Filter': {'Prefix': ''},  # Apply to entire bucket
            'Tierings': [
                {
                    'Days': 90,
                    'AccessTier': 'ARCHIVE_ACCESS'
                },
                {
                    'Days': 180,
                    'AccessTier': 'DEEP_ARCHIVE_ACCESS'
                }
            ]
        }

        s3_client.put_bucket_intelligent_tiering_configuration(
            Bucket=bucket_name,
            Id='EntireBucket',
            IntelligentTieringConfiguration=config
        )

        log(f"Successfully enabled Intelligent-Tiering for {bucket_name}")
        return True

    except ClientError as e:
        log(f"Failed to enable Intelligent-Tiering for {bucket_name}: {e}")
        return False


def clean_incomplete_uploads(s3_client, bucket_name: str, days_old: int, dry_run: bool) -> int:
    """Clean up incomplete multipart uploads older than specified days."""
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        # List incomplete multipart uploads
        response = s3_client.list_multipart_uploads(Bucket=bucket_name)
        uploads = response.get('Uploads', [])

        old_uploads = []
        for upload in uploads:
            if upload['Initiated'] < cutoff_date:
                old_uploads.append(upload)

        if not old_uploads:
            log(f"No incomplete uploads older than {days_old} days in {bucket_name}")
            return 0

        if dry_run:
            log(f"DRY RUN: Would clean up {len(old_uploads)} incomplete uploads in {bucket_name}")
            return len(old_uploads)

        log(f"Cleaning up {len(old_uploads)} incomplete uploads in {bucket_name}")

        cleaned_count = 0
        for upload in old_uploads:
            try:
                s3_client.abort_multipart_upload(
                    Bucket=bucket_name,
                    Key=upload['Key'],
                    UploadId=upload['UploadId']
                )
                cleaned_count += 1
            except ClientError as e:
                log(f"Failed to abort upload {upload['UploadId']}: {e}")

        log(f"Successfully cleaned up {cleaned_count} incomplete uploads in {bucket_name}")
        return cleaned_count

    except ClientError as e:
        log(f"Error cleaning incomplete uploads in {bucket_name}: {e}")
        return 0


def calculate_potential_savings(bucket_info: Dict, transition_to_ia_days: int,
                               transition_to_glacier_days: int) -> Dict:
    """Calculate potential monthly savings from lifecycle policies."""
    size_gb = bucket_info['size_gb']
    current_cost = bucket_info['monthly_cost_standard']

    if size_gb == 0:
        return {'potential_savings': 0, 'optimized_cost': 0}

    # Simplified calculation assuming even distribution of object ages
    # In reality, savings depend on actual object age distribution

    # Assume 30% of objects transition to IA, 20% to Glacier
    standard_portion = 0.5
    ia_portion = 0.3
    glacier_portion = 0.2

    optimized_cost = (
        (size_gb * standard_portion * 0.023) +  # Standard
        (size_gb * ia_portion * 0.0125) +      # Standard-IA
        (size_gb * glacier_portion * 0.0036)   # Glacier
    )

    potential_savings = current_cost - optimized_cost

    return {
        'potential_savings': max(0, potential_savings),
        'optimized_cost': optimized_cost,
        'savings_percentage': (potential_savings / current_cost * 100) if current_cost > 0 else 0
    }


def send_alert(webhook: str, optimization_results: List[Dict], total_savings: float) -> None:
    """Send optimization results to webhook."""
    if not optimization_results:
        return

    total_size = sum(result['bucket_info']['size_gb'] for result in optimization_results)
    total_current_cost = sum(result['bucket_info']['monthly_cost_standard'] for result in optimization_results)

    message_lines = [
        f"S3 Lifecycle Optimization Report",
        f"",
        f"Analyzed {len(optimization_results)} bucket(s)",
        f"Total size: {total_size:,.2f} GB",
        f"Current monthly cost: ${total_current_cost:.2f}",
        f"Potential monthly savings: ${total_savings:.2f}",
    ]

    if total_savings > 0:
        savings_percentage = (total_savings / total_current_cost * 100) if total_current_cost > 0 else 0
        message_lines.append(f"Potential savings: {savings_percentage:.1f}%")

    message_lines.append("")
    message_lines.append("🪣 Bucket Details:")

    for result in optimization_results[:10]:  # Show top 10 buckets
        bucket = result['bucket_info']
        savings = result.get('savings', {})

        if bucket['size_gb'] > 0:
            message_lines.append(
                f"- {bucket['bucket_name']}: {bucket['size_gb']:.2f} GB, "
                f"${bucket['monthly_cost_standard']:.2f}/month, "
                f"potential savings: ${savings.get('potential_savings', 0):.2f}"
            )

    if len(optimization_results) > 10:
        message_lines.append(f"... and {len(optimization_results) - 10} more buckets")

    message_lines.extend([
        f"",
        f"Lifecycle policies help transition objects to cheaper storage",
        f"Consider S3 Intelligent-Tiering for unpredictable access patterns",
        f"Regular cleanup of incomplete uploads saves costs"
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
    log("Starting S3 lifecycle optimization")

    # Configuration
    enable_lifecycle_policies = os.getenv("ENABLE_LIFECYCLE_POLICIES", "false").lower() == "true"
    transition_to_ia_days = int(os.getenv("TRANSITION_TO_IA_DAYS", "30"))
    transition_to_glacier_days = int(os.getenv("TRANSITION_TO_GLACIER_DAYS", "90"))
    enable_intelligent_tiering = os.getenv("ENABLE_INTELLIGENT_TIERING", "false").lower() == "true"
    clean_incomplete_uploads = os.getenv("CLEAN_INCOMPLETE_UPLOADS", "false").lower() == "true"
    incomplete_upload_days = int(os.getenv("INCOMPLETE_UPLOAD_DAYS", "7"))
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    webhook = os.getenv("ALERT_WEBHOOK")

    log(f"Enable lifecycle policies: {enable_lifecycle_policies}")
    log(f"Transition to IA after: {transition_to_ia_days} days")
    log(f"Transition to Glacier after: {transition_to_glacier_days} days")
    log(f"Enable Intelligent-Tiering: {enable_intelligent_tiering}")
    log(f"Clean incomplete uploads: {clean_incomplete_uploads}")
    log(f"Dry run mode: {dry_run}")

    try:
        # Create AWS clients
        s3_client = boto3.client('s3')
        cloudwatch_client = boto3.client('cloudwatch', region_name='us-east-1')  # S3 metrics are in us-east-1

        # Get bucket list
        buckets = get_bucket_list(s3_client)
        log(f"Analyzing {len(buckets)} bucket(s)")

        optimization_results = []
        total_potential_savings = 0

        for bucket_name in buckets:
            # Analyze bucket
            bucket_info = analyze_bucket_storage(s3_client, cloudwatch_client, bucket_name)

            if 'error' in bucket_info:
                log(f"Skipping {bucket_name} due to analysis error")
                continue

            if bucket_info['size_gb'] == 0:
                log(f"Skipping empty bucket: {bucket_name}")
                continue

            # Calculate potential savings
            savings = calculate_potential_savings(
                bucket_info, transition_to_ia_days, transition_to_glacier_days
            )

            result = {
                'bucket_info': bucket_info,
                'savings': savings
            }

            optimization_results.append(result)
            total_potential_savings += savings['potential_savings']

            log(f"  Size: {bucket_info['size_gb']:.2f} GB")
            log(f"  Current cost: ${bucket_info['monthly_cost_standard']:.2f}/month")
            log(f"  Potential savings: ${savings['potential_savings']:.2f}/month")

            # Apply optimizations if enabled
            if enable_lifecycle_policies:
                current_policy = get_current_lifecycle_policy(s3_client, bucket_name)
                if not current_policy:
                    policy = create_lifecycle_policy(
                        transition_to_ia_days, transition_to_glacier_days,
                        incomplete_upload_days if clean_incomplete_uploads else 0
                    )
                    apply_lifecycle_policy(s3_client, bucket_name, policy, dry_run)
                else:
                    log(f"Bucket {bucket_name} already has a lifecycle policy")

            if enable_intelligent_tiering:
                enable_intelligent_tiering(s3_client, bucket_name, dry_run)

            if clean_incomplete_uploads:
                cleaned_count = clean_incomplete_uploads(
                    s3_client, bucket_name, incomplete_upload_days, dry_run
                )
                if cleaned_count > 0:
                    log(f"Cleaned up {cleaned_count} incomplete uploads in {bucket_name}")

        # Summary
        log(f"")
        log(f"=== S3 LIFECYCLE OPTIMIZATION SUMMARY ===")
        log(f"Total buckets analyzed: {len(optimization_results)}")

        if optimization_results:
            total_size = sum(r['bucket_info']['size_gb'] for r in optimization_results)
            total_current_cost = sum(r['bucket_info']['monthly_cost_standard'] for r in optimization_results)

            log(f"Total size: {total_size:,.2f} GB")
            log(f"Current monthly cost: ${total_current_cost:.2f}")
            log(f"Potential monthly savings: ${total_potential_savings:.2f}")

            if total_current_cost > 0:
                savings_percentage = total_potential_savings / total_current_cost * 100
                log(f"Potential savings percentage: {savings_percentage:.1f}%")

        # Send alert
        if webhook and optimization_results:
            send_alert(webhook, optimization_results, total_potential_savings)

        return 0

    except NoCredentialsError:
        log("ERROR: AWS credentials not configured")
        return 1
    except Exception as exc:
        log(f"S3 lifecycle optimization failed: {exc}")
        return 1

    log("S3 lifecycle optimization completed")


if __name__ == "__main__":
    sys.exit(main())
