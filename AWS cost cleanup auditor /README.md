# 🧹 AWS Cost & Security Cleanup Script

This Python script scans your AWS account for **unused or idle resources** that may generate unnecessary costs.  
It generates a **consolidated CSV report** with severity scores so you can quickly prioritize cleanup.

---

## ✅ Features
The script checks for the following resources:
- **Unattached EBS Volumes** (High severity)
- **Old EBS Snapshots (>90 days)** (Medium severity)
- **Unattached Elastic IPs** (High severity)
- **Unused Load Balancers (Classic, ALB, NLB)** (High severity)
- **Idle RDS Instances** (Low / Medium / High based on usage)
- **Stopped EC2 Instances** (Medium severity)

---

## 📊 Output

When you run the script, it prints a summary:

🔍 Checking unused EBS volumes...
🔍 Checking old EBS snapshots (>90 days)...
🔍 Checking unattached Elastic IPs...
🔍 Checking unused Load Balancers...
🔍 Checking idle RDS instances...
🔍 Checking stopped EC2 instances...
✅ Report saved: aws_cost_audit_summary.csv

📊 Summary:
Unattached Volumes: 2
Old Snapshots (>90 days): 3
Unattached Elastic IPs: 1
Unused Load Balancers: 1
Idle RDS instances: 2
Stopped EC2 instances: 4


And generates a CSV file: aws_cost_audit_summary.csv

| ResourceType | Name          | ResourceId    | Details                                                    | Severity |
|--------------|--------------|---------------|------------------------------------------------------------|----------|
| EBS Volume   | data-backup  | vol-0a123b456 | Size=100GiB, State=available, AZ=us-east-1a                | High     |
| Elastic IP   | 54.123.45.67 | eipalloc-0ab1 | Domain=vpc                                                 | High     |
| RDS Instance | prod-db      | mydb1         | mysql db.t3.medium Status=available Storage=200GiB         | High     |
| EC2 Instance | webserver-01 | i-0123456789a | Type=t3.medium AZ=us-east-1a State=stopped                 | Medium   |

---

## ⚡️ Prerequisites

- Python **3.8+**
- AWS CLI configured (aws configure)
- Boto3 library installed

pip install boto3
The script uses your default AWS CLI profile & region unless otherwise configured.

🚀 How to Run
Clone this repo or copy the script file (e.g., aws_cleanup_audit.py).

Run the script:
python aws_cleanup_audit.py

After completion, check the CSV file:
aws_cost_audit_summary.csv

You can open it in Excel / Google Sheets for easier filtering & sorting.

🛡️ Severity Levels
High → Immediate cost impact (Unattached Volumes, Elastic IPs, unused LB, big RDS).

Medium → Potential cost (Stopped EC2, old Snapshots).

Low → Low-priority findings.

⚠️ Disclaimer
This script is read-only:
It does not delete or stop any resources automatically.
Use the findings to manually clean up unused AWS resources.

