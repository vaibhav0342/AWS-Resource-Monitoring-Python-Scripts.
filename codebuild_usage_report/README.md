1. Prerequisites

Make sure your system meets these requirements:

Python 3.9+ installed

AWS CLI v2 configured (credentials and default region)

Python packages: boto3, pandas

Install the required Python packages:

pip install boto3 pandas


Check AWS CLI configuration:

aws configure


Optionally, if you use multiple AWS accounts, make sure you have profiles configured:

aws configure --profile myprofile

2. Save the Script

Save the Python script as codebuild_usage_report_parallel.py in your working directory.

Make it executable (optional):

chmod +x codebuild_usage_report_parallel.py

3. Run the Script Locally

Basic run (default region us-east-1, last 30 days):

python3 codebuild_usage_report_parallel.py

4. Run with Custom Options

Scan multiple regions, last 60 days:

python3 codebuild_usage_report_parallel.py --regions us-east-1 us-west-2 --days 60


Use a specific AWS profile:

python3 codebuild_usage_report_parallel.py --profile myprofile


Upload the report to S3:

python3 codebuild_usage_report_parallel.py --s3-bucket my-report-bucket


Set maximum parallel threads:

python3 codebuild_usage_report_parallel.py --threads 15


You can combine options:

python3 codebuild_usage_report_parallel.py \
  --regions us-east-1 us-west-2 \
  --days 30 \
  --profile myprofile \
  --s3-bucket my-report-bucket \
  --threads 10

5. Output

After the script finishes, it generates:

CSV report: codebuild_report_YYYYMMDD_HHMMSS.csv

JSON report: codebuild_report_YYYYMMDD_HHMMSS.json

Example CSV:

ProjectName,Status,LastBuildTime,Region,SourceType,EnvironmentImage
frontend,USED,2025-10-06T12:45:22,us-east-1,GITHUB,aws/codebuild/standard:6.0
backend,UNUSED,2025-08-10T10:15:00,us-east-1,GITHUB,aws/codebuild/standard:6.0
legacy,EMPTY,N/A,us-east-1,NO_SOURCE,None


If --s3-bucket is specified, the reports are uploaded to your S3 bucket.
