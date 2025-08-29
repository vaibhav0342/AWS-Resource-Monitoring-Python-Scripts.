#!/usr/bin/env python3
"""
************************** VAIBHAV UPARE *******************************
EC2 inventory:
- Scans all enabled regions
- Gathers rich EC2 details, SGs, ENIs, volumes, tags
- Writes CSV and Excel (table format)

Usage:
  pip install boto3 pandas xlsxwriter
  python ec2_inventory.py          # uses default AWS creds/role/profile
  AWS_PROFILE=yourprofile python ec2_inventory.py
"""

import boto3
import botocore
import pandas as pd
from datetime import datetime, timezone
from collections import defaultdict

# ---------- Helpers ----------

def safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if cur is None:
            return default
        cur = cur.get(k)
    return cur if cur is not None else default

def iso_or_none(dt):
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

def days_between(start):
    if not isinstance(start, datetime):
        return None
    return (datetime.now(timezone.utc) - start).days

def flatten_tags(tags):
    # Returns dict like {"tag_Name":"web", "tag_Env":"prod"}
    out = {}
    if isinstance(tags, list):
        for t in tags:
            k = t.get("Key")
            v = t.get("Value")
            if k:
                out[f"tag_{k}"] = v
    return out

def get_ami_names(ec2_client, image_ids):
    # Batch-fetch AMI names; returns dict: {imageId: name}
    ami_map = {}
    if not image_ids:
        return ami_map
    # API allows up to 100 image IDs per call
    ids = list({i for i in image_ids if i})
    for i in range(0, len(ids), 100):
        chunk = ids[i:i+100]
        try:
            resp = ec2_client.describe_images(ImageIds=chunk)
            for img in resp.get("Images", []):
                ami_map[img["ImageId"]] = img.get("Name")
        except botocore.exceptions.ClientError:
            # Some AMIs may be owned by other accounts/marketplace; ignore if access denied
            continue
    return ami_map

def volumes_by_instance(ec2_client, instance_ids):
    # Map instanceId -> list of volume dicts
    result = defaultdict(list)
    if not instance_ids:
        return result
    paginator = ec2_client.get_paginator("describe_volumes")
    try:
        for page in paginator.paginate(
            Filters=[{"Name":"attachment.instance-id", "Values":instance_ids}]
        ):
            for vol in page.get("Volumes", []):
                for att in vol.get("Attachments", []):
                    iid = att.get("InstanceId")
                    if iid:
                        result[iid].append({
                            "VolumeId": vol.get("VolumeId"),
                            "SizeGiB": vol.get("Size"),
                            "VolumeType": vol.get("VolumeType"),
                            "Iops": vol.get("Iops"),
                            "Throughput": vol.get("Throughput"),
                            "Encrypted": vol.get("Encrypted"),
                            "KmsKeyId": vol.get("KmsKeyId"),
                            "DeviceName": att.get("Device"),
                            "DeleteOnTermination": att.get("DeleteOnTermination"),
                            "AttachTime": iso_or_none(att.get("AttachTime")),
                        })
    except botocore.exceptions.ClientError:
        pass
    return result

def enis_by_instance(ec2_client, instance_ids):
    # Map instanceId -> list of ENI dicts
    result = defaultdict(list)
    if not instance_ids:
        return result
    paginator = ec2_client.get_paginator("describe_network_interfaces")
    try:
        for page in paginator.paginate(
            Filters=[{"Name": "attachment.instance-id", "Values": instance_ids}]
        ):
            for eni in page.get("NetworkInterfaces", []):
                result[safe_get(eni, "Attachment", "InstanceId")].append({
                    "NetworkInterfaceId": eni.get("NetworkInterfaceId"),
                    "MacAddress": eni.get("MacAddress"),
                    "PrivateIpAddress": eni.get("PrivateIpAddress"),
                    "PrivateDnsName": eni.get("PrivateDnsName"),
                    "PublicIp": safe_get(eni, "Association", "PublicIp"),
                    "PublicDnsName": safe_get(eni, "Association", "PublicDnsName"),
                    "InterfaceType": eni.get("InterfaceType"),
                    "Status": eni.get("Status"),
                    "SubnetId": eni.get("SubnetId"),
                    "VpcId": eni.get("VpcId"),
                })
    except botocore.exceptions.ClientError:
        pass
    return result

# ---------- Main ----------

def main():
    session = boto3.Session()
    sts = session.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    ec2_global = session.client("ec2", region_name="us-east-1")

    # all enabled regions
    regions = [r["RegionName"] for r in ec2_global.describe_regions(AllRegions=False)["Regions"]]

    rows = []

    for region in regions:
        ec2 = session.client("ec2", region_name=region)

        # Enumerate instances (running or any state)
        paginator = ec2.get_paginator("describe_instances")
        reservations = []
        for page in paginator.paginate():
            reservations.extend(page.get("Reservations", []))

        # Gather for AMI and resource joining
        instances = []
        image_ids = set()
        instance_ids = []

        for res in reservations:
            for inst in res.get("Instances", []):
                instances.append(inst)
                instance_ids.append(inst["InstanceId"])
                img = inst.get("ImageId")
                if img:
                    image_ids.add(img)

        ami_names = get_ami_names(ec2, image_ids)
        vols_map = volumes_by_instance(ec2, instance_ids)
        enis_map = enis_by_instance(ec2, instance_ids)

        for inst in instances:
            iid = inst["InstanceId"]
            name_tag = next((t["Value"] for t in inst.get("Tags", []) if t.get("Key") == "Name"), None)

            # Security groups (IDs + names)
            sg_ids = []
            sg_names = []
            for sg in inst.get("SecurityGroups", []):
                sg_ids.append(sg.get("GroupId"))
                sg_names.append(sg.get("GroupName"))

            # Root device info
            block_map = inst.get("BlockDeviceMappings", []) or []
            root_dev_name = inst.get("RootDeviceName")
            root_dev_type = inst.get("RootDeviceType")

            # Volumes summary string
            vol_list = vols_map.get(iid, [])
            vol_summary = "; ".join(
                f"{v['VolumeId']}({v['SizeGiB']}GiB {v['VolumeType']}"
                + (f" {v['Iops']}iops" if v.get('Iops') is not None else "")
                + (f" {v['Throughput']}MB/s" if v.get('Throughput') is not None else "")
                + f", {v['DeviceName']})"
                for v in vol_list
            ) if vol_list else ""

            # ENIs summary
            eni_list = enis_map.get(iid, [])
            eni_summary = "; ".join(
                f"{e['NetworkInterfaceId']}({e['PrivateIpAddress']}"
                + (f", pub:{e['PublicIp']}" if e.get('PublicIp') else "")
                + f", mac:{e['MacAddress']})"
                for e in eni_list
            ) if eni_list else ""

            launch_time = inst.get("LaunchTime")
            row = {
                "AccountId": account_id,
                "Region": region,
                "InstanceId": iid,
                "Name": name_tag,
                "State": safe_get(inst, "State", "Name"),
                "Platform": inst.get("Platform") or "Linux/UNIX",
                "Architecture": inst.get("Architecture"),
                "Hypervisor": inst.get("Hypervisor"),
                "ImageId": inst.get("ImageId"),
                "ImageName": ami_names.get(inst.get("ImageId")),
                "InstanceType": inst.get("InstanceType"),
                "CPU_Cores": safe_get(inst, "CpuOptions", "CoreCount"),
                "CPU_ThreadsPerCore": safe_get(inst, "CpuOptions", "ThreadsPerCore"),
                "AvailabilityZone": safe_get(inst, "Placement", "AvailabilityZone"),
                "Tenancy": safe_get(inst, "Placement", "Tenancy"),
                "PlacementGroup": safe_get(inst, "Placement", "GroupName"),
                "PrivateIpAddress": inst.get("PrivateIpAddress"),
                "PrivateDnsName": inst.get("PrivateDnsName"),
                "PublicIpAddress": inst.get("PublicIpAddress"),
                "PublicDnsName": inst.get("PublicDnsName"),
                "VpcId": inst.get("VpcId"),
                "SubnetId": inst.get("SubnetId"),
                "IamInstanceProfileArn": safe_get(inst, "IamInstanceProfile", "Arn"),
                "RootDeviceName": root_dev_name,
                "RootDeviceType": root_dev_type,
                "EbsOptimized": inst.get("EbsOptimized"),
                "LaunchTime": iso_or_none(launch_time),
                "UptimeDays": days_between(launch_time),
                "SecurityGroupIds": ", ".join(sg_ids) if sg_ids else None,
                "SecurityGroupNames": ", ".join(sg_names) if sg_names else None,
                "BlockDeviceCount": len(block_map),
                "Volumes": vol_summary,
                "ENIs": eni_summary,
            }

            # Add flattened tags as columns
            row.update(flatten_tags(inst.get("Tags", [])))
            rows.append(row)

    # Build DataFrame and save
    df = pd.DataFrame(rows)

    # Sort columns: core first, tags later
    core_cols = [
        "AccountId","Region","InstanceId","Name","State","Platform","Architecture","Hypervisor",
        "ImageId","ImageName","InstanceType","CPU_Cores","CPU_ThreadsPerCore",
        "AvailabilityZone","Tenancy","PlacementGroup",
        "PrivateIpAddress","PrivateDnsName","PublicIpAddress","PublicDnsName",
        "VpcId","SubnetId","IamInstanceProfileArn",
        "RootDeviceName","RootDeviceType","EbsOptimized",
        "LaunchTime","UptimeDays",
        "SecurityGroupIds","SecurityGroupNames","BlockDeviceCount","Volumes","ENIs"
    ]
    tag_cols = [c for c in df.columns if c.startswith("tag_")]
    other_cols = [c for c in df.columns if c not in core_cols + tag_cols]
    df = df[core_cols + other_cols + tag_cols]

    df.sort_values(["Region","Name","InstanceId"], inplace=True, na_position="last")

    csv_path = "ec2_inventory.csv"
    xlsx_path = "ec2_inventory.xlsx"

    df.to_csv(csv_path, index=False)

    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="EC2")
        # Optional: turn range into an Excel table for nicer filtering
        wb  = writer.book
        ws  = writer.sheets["EC2"]
        rows_count, cols_count = df.shape
        ws.add_table(0, 0, rows_count, cols_count-1, {
            "name": "EC2Inventory",
            "columns": [{"header": col} for col in df.columns],
            "style": {"theme":"Table Style Medium 9"}
        })
        ws.freeze_panes(1, 0)
        # Auto-fit columns (approx)
        for i, col in enumerate(df.columns):
            maxw = max(10, min(60, int(df[col].astype(str).map(len).max() if not df.empty else 10) + 2))
            ws.set_column(i, i, maxw)

    print(f"✅ Wrote {csv_path} and {xlsx_path} with {len(df)} instances.")

if __name__ == "__main__":
    main()
