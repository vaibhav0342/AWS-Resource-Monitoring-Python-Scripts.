🛡️ S3 Bucket Security Checker

This script scans all S3 buckets in your AWS account and generates a CSV report with security findings such as:

Public Access (via ACL or Bucket Policy)

Server-Side Encryption status

Versioning status

Access Logging status

Severity Score (High / Medium / Low)

📋 Prerequisites

Python 3.7+ installed
Check with:

python3 --version


boto3 library installed
Install via pip:
apt install python3.12-venv
python3 -m venv ~/checkov-venv
source ~/checkov-venv/bin/activate
pip install boto3


AWS CLI configured with valid credentials and permissions:

aws configure


You’ll need at least these IAM permissions:

s3:ListAllMyBuckets

s3:GetBucketAcl

s3:GetBucketPolicyStatus

s3:GetBucketEncryption

s3:GetBucketVersioning

s3:GetBucketLogging

▶️ How to Run

Save the script as s3_security_check.py.

Run the script:

python3 s3_security_check.py


After it completes, you’ll see:

✅ Security check completed. Report saved as s3_bucket_security_report.csv

📊 Output

The script creates a CSV file: s3_bucket_security_report.csv

Example:

Bucket	PublicAccessBlock	ACL_Public	Policy_Public	Encryption	Versioning	Logging	Severity
app-logs-prod	Restricted	False	False	Enabled	Enabled	Disabled	Medium
test-public	Public	True	True	Disabled	Disabled	Disabled	High
private-data	Restricted	False	False	Enabled	Enabled	Enabled	Low
⚠️ Notes

Buckets with High severity should be remediated immediately (e.g., disable public access, enable encryption).

Medium severity issues are recommended best practices.

Low severity means the bucket is aligned with AWS best practices.
