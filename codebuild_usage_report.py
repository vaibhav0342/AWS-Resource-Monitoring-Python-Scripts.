#!/usr/bin/env python3
"""
AWS CodeBuild Usage Report - Parallel Production Ready
# Scan 2 regions with 10 threads, last 30 days
python3 codebuild_usage_report_parallel.py --regions us-east-1 us-west-2 --days 30 --threads 10

# Scan and upload to S3 using a profile
python3 codebuild_usage_report_parallel.py --regions us-east-1 --days 30 --profile myprofile --s3-bucket my-report-bucket --threads 15


Generates a report of all AWS CodeBuild projects showing:
- USED    = Builds executed in the last N days
- UNUSED  = Has builds, but none in last N days
- EMPTY   = No builds and/or no source/environment defined

Features:
- Multi-region support
- Parallel project processing (ThreadPoolExecutor)
- Retry logic and pagination
- CSV & JSON output
- Optional S3 upload
- Optional AWS profile
"""

import boto3
import botocore
import pandas as pd
import argparse
import datetime
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from botocore.config import Config

# ------------------------ Configuration ------------------------
RETRY_CONFIG = Config(
    retries={
        'max_attempts': 5,
        'mode': 'standard'
    }
)
MAX_THREADS = 10  # Number of threads for parallel processing

# ------------------------ Utility Functions ------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="AWS CodeBuild Usage Report")
    parser.add_argument('--regions', nargs='+', default=['us-east-1'], help='AWS regions to scan')
    parser.add_argument('--days', type=int, default=30, help='Days to consider a build as recent')
    parser.add_argument('--s3-bucket', type=str, help='Optional S3 bucket to upload reports')
    parser.add_argument('--profile', type=str, help='AWS CLI profile to use')
    parser.add_argument('--output-prefix', type=str, default='codebuild_report', help='Output file prefix')
    parser.add_argument('--threads', type=int, default=MAX_THREADS, help='Max threads for parallel processing')
    return parser.parse_args()


def get_boto3_client(service, region, profile=None):
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return session.client(service, region_name=region, config=RETRY_CONFIG)


def paginate_list_projects(client):
    projects = []
    paginator = client.get_paginator('list_projects')
    for page in paginator.paginate():
        projects.extend(page.get('projects', []))
    return projects


def paginate_list_builds(client, project_name):
    builds = []
    paginator = client.get_paginator('list_builds_for_project')
    for page in paginator.paginate(projectName=project_name):
        builds.extend(page.get('ids', []))
    return builds


def get_project_details(client, project_names):
    if not project_names:
        return []
    resp = client.batch_get_projects(names=project_names)
    return resp.get('projects', [])


def get_build_details(client, build_ids):
    if not build_ids:
        return []
    resp = client.batch_get_builds(ids=build_ids)
    return resp.get('builds', [])


def determine_status(last_build_time, days_threshold):
    if not last_build_time:
        return "EMPTY"
    now = datetime.datetime.utcnow()
    diff = now - last_build_time
    return "USED" if diff.days <= days_threshold else "UNUSED"


def process_project(project, client, days_threshold, region):
    try:
        project_name = project['name']
        source_type = project.get('source', {}).get('type', 'NO_SOURCE')
        env_image = project.get('environment', {}).get('image', None)

        # Get all build IDs
        build_ids = paginate_list_builds(client, project_name)
        last_build_time = None

        if build_ids:
            builds_detail = get_build_details(client, [build_ids[0]])
            if builds_detail:
                last_build_str = builds_detail[0].get('startTime')
                if last_build_str:
                    last_build_time = last_build_str.replace(tzinfo=None)

        status = determine_status(last_build_time, days_threshold)
        if status == "EMPTY" and (source_type != "NO_SOURCE" and env_image):
            status = "UNUSED"

        return {
            "ProjectName": project_name,
            "Status": status,
            "LastBuildTime": last_build_time.isoformat() if last_build_time else "N/A",
            "Region": region,
            "SourceType": source_type,
            "EnvironmentImage": env_image
        }
    except Exception as e:
        print(f"Error processing project {project.get('name', 'N/A')}: {e}", file=sys.stderr)
        return None

# ------------------------ Main Logic ------------------------
def main():
    args = parse_args()
    report_data = []

    for region in args.regions:
        print(f"Scanning region: {region}")
        client = get_boto3_client('codebuild', region, args.profile)

        try:
            project_names = paginate_list_projects(client)
            if not project_names:
                print(f"No CodeBuild projects found in {region}")
                continue

            projects = get_project_details(client, project_names)

            # Parallel processing of projects
            with ThreadPoolExecutor(max_workers=args.threads) as executor:
                futures = [executor.submit(process_project, p, client, args.days, region) for p in projects]
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        report_data.append(result)

        except botocore.exceptions.ClientError as e:
            print(f"Error accessing region {region}: {e}", file=sys.stderr)
            continue

    # ------------------------ Save Reports ------------------------
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    csv_file = f"{args.output_prefix}_{timestamp}.csv"
    json_file = f"{args.output_prefix}_{timestamp}.json"

    df = pd.DataFrame(report_data)
    df.to_csv(csv_file, index=False)
    with open(json_file, 'w') as f:
        json.dump(report_data, f, indent=2)

    print(f"Reports saved: {csv_file}, {json_file}")

    # Optional S3 upload
    if args.s3_bucket:
        s3_client = get_boto3_client('s3', args.regions[0], args.profile)
        s3_client.upload_file(csv_file, args.s3_bucket, csv_file)
        s3_client.upload_file(json_file, args.s3_bucket, json_file)
        print(f"Reports uploaded to s3://{args.s3_bucket}/")

    print("✅ CodeBuild usage report completed.")


if __name__ == "__main__":
    main()

