#!/usr/bin/env python3
"""
*************************************** VAIBHAV UPARE *********************************
RDS_inventory.py
Inventory all rds details.
python3 --version
aws configure
pip install boto3 pandas openpyxl
python3 rds_inventory.py

"""

import boto3
import pandas as pd
from datetime import datetime

session = boto3.Session(region_name="us-east-1")  # Change default region if needed
rds = session.client("rds")
sts = session.client("sts")

# Get account ID
account_id = sts.get_caller_identity()["Account"]

all_data = []

# Get all regions where RDS is available
ec2 = session.client("ec2")
regions = [r["RegionName"] for r in ec2.describe_regions()["Regions"]]

for region in regions:
    print(f"🔍 Scanning region: {region}")
    rds_regional = boto3.client("rds", region_name=region)
    try:
        instances = rds_regional.describe_db_instances()["DBInstances"]
    except Exception as e:
        print(f"Error in {region}: {e}")
        continue

    for db in instances:
        # Basic RDS details
        db_id = db["DBInstanceIdentifier"]
        engine = db["Engine"]
        engine_ver = db["EngineVersion"]
        status = db["DBInstanceStatus"]
        created = db["InstanceCreateTime"].strftime("%Y-%m-%d %H:%M:%S")

        # Storage
        allocated = db.get("AllocatedStorage")
        storage_type = db.get("StorageType")
        iops = db.get("Iops")

        # Networking
        az = db.get("AvailabilityZone")
        multi_az = db.get("MultiAZ")
        vpc = db.get("DBSubnetGroup", {}).get("VpcId")
        subnet_group = db.get("DBSubnetGroup", {}).get("DBSubnetGroupName")
        endpoint = None
        port = None
        if "Endpoint" in db:
            endpoint = db["Endpoint"].get("Address")
            port = db["Endpoint"].get("Port")

        # Security Groups
        sg_ids = []
        sg_names = []
        for vpcsg in db.get("VpcSecurityGroups", []):
            sg_ids.append(vpcsg.get("VpcSecurityGroupId"))
            sg_names.append(vpcsg.get("Status"))

        # Backup & Maintenance
        backup_window = db.get("PreferredBackupWindow")
        maint_window = db.get("PreferredMaintenanceWindow")

        # Tags
        tags_resp = rds_regional.list_tags_for_resource(ResourceName=db["DBInstanceArn"])
        tags = {t["Key"]: t["Value"] for t in tags_resp.get("TagList", [])}

        all_data.append({
            "AccountId": account_id,
            "Region": region,
            "DBIdentifier": db_id,
            "Engine": engine,
            "EngineVersion": engine_ver,
            "Status": status,
            "InstanceClass": db["DBInstanceClass"],
            "AllocatedStorage(GB)": allocated,
            "StorageType": storage_type,
            "IOPS": iops,
            "AvailabilityZone": az,
            "MultiAZ": multi_az,
            "VpcId": vpc,
            "SubnetGroup": subnet_group,
            "Endpoint": endpoint,
            "Port": port,
            "SecurityGroupIds": ",".join(filter(None, sg_ids)),
            "SecurityGroupStatus": ",".join(filter(None, sg_names)),
            "BackupWindow": backup_window,
            "MaintenanceWindow": maint_window,
            "CreatedTime": created,
            **{f"tag_{k}": v for k, v in tags.items()}  # include tags dynamically
        })

# Convert to DataFrame
df = pd.DataFrame(all_data)

# Save to CSV
csv_file = f"rds_inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
df.to_csv(csv_file, index=False)

# Save to Excel
excel_file = f"rds_inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
    df.to_excel(writer, sheet_name="RDS Inventory", index=False)

print(f"\n✅ Inventory complete. Files saved:\n - {csv_file}\n - {excel_file}")
