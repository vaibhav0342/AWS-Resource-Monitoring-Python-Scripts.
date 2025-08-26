import boto3
import csv
from datetime import datetime, timezone, timedelta

def get_name_tag(tags):
    if not tags:
        return ""
    for t in tags:
        if t["Key"] == "Name":
            return t["Value"]
    return ""

def list_unused_volumes(ec2):
    unused_vols = []
    for v in ec2.volumes.all():
        if not v.attachments:
            unused_vols.append({
                "ResourceType": "EBS Volume",
                "Name": get_name_tag(v.tags),
                "ResourceId": v.id,
                "Details": f"Size={v.size}GiB, State={v.state}, AZ={v.availability_zone}",
                "Severity": "High"
            })
    return unused_vols

def list_old_snapshots(ec2_client, days_old=90):
    old_snaps = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
    snapshots = ec2_client.describe_snapshots(OwnerIds=['self'])["Snapshots"]
    for snap in snapshots:
        if snap["StartTime"] < cutoff:
            old_snaps.append({
                "ResourceType": "EBS Snapshot",
                "Name": (snap.get("Tags", [{}])[0].get("Value","") if snap.get("Tags") else ""),
                "ResourceId": snap["SnapshotId"],
                "Details": f"Volume={snap.get('VolumeId','N/A')}, Size={snap['VolumeSize']}GiB, Started={snap['StartTime'].strftime('%Y-%m-%d')}",
                "Severity": "Medium"
            })
    return old_snaps

def list_unattached_eips(ec2_client):
    eips = []
    addresses = ec2_client.describe_addresses()["Addresses"]
    for addr in addresses:
        if "AssociationId" not in addr:
            eips.append({
                "ResourceType": "Elastic IP",
                "Name": addr.get("PublicIp"),
                "ResourceId": addr.get("AllocationId","N/A"),
                "Details": f"Domain={addr.get('Domain','standard')}",
                "Severity": "High"
            })
    return eips

def list_unused_load_balancers(elb_client, elbv2_client):
    unused = []
    lbs = elb_client.describe_load_balancers()["LoadBalancerDescriptions"]
    for lb in lbs:
        if not lb["Instances"]:
            unused.append({
                "ResourceType": "Classic ELB",
                "Name": lb["LoadBalancerName"],
                "ResourceId": lb["LoadBalancerName"],
                "Details": "No instances attached",
                "Severity": "High"
            })
    lbs_v2 = elbv2_client.describe_load_balancers()["LoadBalancers"]
    for lb in lbs_v2:
        tg_resp = elbv2_client.describe_target_groups(LoadBalancerArn=lb["LoadBalancerArn"])
        if tg_resp["TargetGroups"]:
            tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]
            tg = elbv2_client.describe_target_health(TargetGroupArn=tg_arn)
            if not tg["TargetHealthDescriptions"]:
                unused.append({
                    "ResourceType": f"{lb['Type']} Load Balancer",
                    "Name": lb["LoadBalancerName"],
                    "ResourceId": lb["LoadBalancerArn"],
                    "Details": "No targets registered",
                    "Severity": "High"
                })
    return unused

def list_idle_rds(rds_client):
    idle = []
    instances = rds_client.describe_db_instances()["DBInstances"]
    for db in instances:
        sev = "Low"
        if db["DBInstanceStatus"] != "available":
            sev = "Medium"
        elif db["AllocatedStorage"] > 100:
            sev = "High"

        idle.append({
            "ResourceType": "RDS Instance",
            "Name": next((t["Value"] for t in db.get("TagList", []) if t["Key"]=="Name"), ""),
            "ResourceId": db["DBInstanceIdentifier"],
            "Details": f"{db['Engine']} {db['DBInstanceClass']} Status={db['DBInstanceStatus']} Storage={db['AllocatedStorage']}GiB",
            "Severity": sev
        })
    return idle

def list_stopped_instances(ec2_client):
    stopped = []
    reservations = ec2_client.describe_instances(Filters=[{"Name":"instance-state-name","Values":["stopped"]}])["Reservations"]
    for res in reservations:
        for inst in res["Instances"]:
            name = next((t["Value"] for t in inst.get("Tags",[]) if t["Key"]=="Name"), "")
            stopped.append({
                "ResourceType": "EC2 Instance",
                "Name": name,
                "ResourceId": inst["InstanceId"],
                "Details": f"Type={inst['InstanceType']} AZ={inst['Placement']['AvailabilityZone']} State=stopped",
                "Severity": "Medium"
            })
    return stopped

def save_to_csv(filename, data, fieldnames):
    if not data:
        print(f"⚠️ No data for {filename}")
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"✅ Report saved: {filename}")

def main():
    session = boto3.Session()
    ec2 = session.resource("ec2")
    ec2_client = session.client("ec2")
    elb_client = session.client("elb")
    elbv2_client = session.client("elbv2")
    rds_client = session.client("rds")

    master_list = []

    print("🔍 Checking unused EBS volumes...")
    unused_volumes = list_unused_volumes(ec2)
    master_list.extend(unused_volumes)

    print("🔍 Checking old EBS snapshots (>90 days)...")
    old_snapshots = list_old_snapshots(ec2_client)
    master_list.extend(old_snapshots)

    print("🔍 Checking unattached Elastic IPs...")
    eips = list_unattached_eips(ec2_client)
    master_list.extend(eips)

    print("🔍 Checking unused Load Balancers...")
    lbs = list_unused_load_balancers(elb_client, elbv2_client)
    master_list.extend(lbs)

    print("🔍 Checking idle RDS instances...")
    rds_idle = list_idle_rds(rds_client)
    master_list.extend(rds_idle)

    print("🔍 Checking stopped EC2 instances...")
    stopped_instances = list_stopped_instances(ec2_client)
    master_list.extend(stopped_instances)

    # Save consolidated report
    save_to_csv("aws_cost_audit_summary.csv", master_list, ["ResourceType","Name","ResourceId","Details","Severity"])

    print("\n📊 Summary:")
    print(f"Unattached Volumes: {len(unused_volumes)}")
    print(f"Old Snapshots (>90 days): {len(old_snapshots)}")
    print(f"Unattached Elastic IPs: {len(eips)}")
    print(f"Unused Load Balancers: {len(lbs)}")
    print(f"Idle RDS instances: {len(rds_idle)}")
    print(f"Stopped EC2 instances: {len(stopped_instances)}")
    print(f"\n✅ Consolidated report saved as aws_cost_audit_summary.csv")

if __name__ == "__main__":
    main()
