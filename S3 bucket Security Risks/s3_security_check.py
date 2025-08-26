import boto3
import csv
from botocore.exceptions import ClientError

def check_bucket_security(bucket_name, s3_client):
    findings = {
        "Bucket": bucket_name,
        "PublicAccessBlock": "Unknown",
        "ACL_Public": False,
        "Policy_Public": False,
        "Encryption": "Disabled",
        "Versioning": "Disabled",
        "Logging": "Disabled",
        "Severity": "Low"
    }

    # Check Public Access Block
    try:
        pab = s3_client.get_bucket_policy_status(Bucket=bucket_name)
        findings["Policy_Public"] = pab["PolicyStatus"]["IsPublic"]
    except ClientError:
        findings["Policy_Public"] = False

    try:
        pab_config = s3_client.get_bucket_policy_status(Bucket=bucket_name)
        findings["PublicAccessBlock"] = "Restricted" if not pab_config["PolicyStatus"]["IsPublic"] else "Public"
    except ClientError:
        findings["PublicAccessBlock"] = "NotConfigured"

    # Check ACL
    try:
        acl = s3_client.get_bucket_acl(Bucket=bucket_name)
        for grant in acl["Grants"]:
            grantee = grant.get("Grantee", {})
            if grantee.get("URI") == "http://acs.amazonaws.com/groups/global/AllUsers":
                findings["ACL_Public"] = True
    except ClientError:
        pass

    # Check Encryption
    try:
        enc = s3_client.get_bucket_encryption(Bucket=bucket_name)
        rules = enc["ServerSideEncryptionConfiguration"]["Rules"]
        if rules:
            findings["Encryption"] = "Enabled"
    except ClientError:
        findings["Encryption"] = "Disabled"

    # Check Versioning
    try:
        versioning = s3_client.get_bucket_versioning(Bucket=bucket_name)
        if versioning.get("Status") == "Enabled":
            findings["Versioning"] = "Enabled"
    except ClientError:
        pass

    # Check Logging
    try:
        logging = s3_client.get_bucket_logging(Bucket=bucket_name)
        if logging.get("LoggingEnabled"):
            findings["Logging"] = "Enabled"
    except ClientError:
        pass

    # Assign Severity
    if findings["ACL_Public"] or findings["Policy_Public"] or findings["Encryption"] == "Disabled":
        findings["Severity"] = "High"
    elif findings["Versioning"] == "Disabled" or findings["Logging"] == "Disabled":
        findings["Severity"] = "Medium"
    else:
        findings["Severity"] = "Low"

    return findings

def main():
    session = boto3.Session()
    s3_client = session.client("s3")

    # Get all buckets
    buckets = s3_client.list_buckets().get("Buckets", [])
    print(f"Found {len(buckets)} buckets.")

    all_findings = []
    for b in buckets:
        name = b["Name"]
        print(f"🔍 Checking {name}...")
        findings = check_bucket_security(name, s3_client)
        all_findings.append(findings)

    # Save results to CSV
    if all_findings:
        with open("s3_bucket_security_report.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_findings[0].keys())
            writer.writeheader()
            writer.writerows(all_findings)

        print("\n✅ Security check completed. Report saved as s3_bucket_security_report.csv")
    else:
        print("⚠️ No buckets found.")

if __name__ == "__main__":
    main()
