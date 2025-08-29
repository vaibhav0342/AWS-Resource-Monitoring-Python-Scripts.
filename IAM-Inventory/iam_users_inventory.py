#!/usr/bin/env python3
"""
*************************************** VAIBHAV UPARE ******************************************
iam_users_inventory.py
Inventory all IAM users with rich user-level details.
python3 --version
aws configure
pip install boto3 pandas openpyxl
python3 iam_users_inventory.py

Outputs:
  - iam_users_<timestamp>.csv
  - iam_users_<timestamp>.xlsx  (sheet: Users, sheet: AccessKeys)

Usage:
  python iam_users_inventory.py
"""

import boto3
import botocore
import pandas as pd
from datetime import datetime
from collections import defaultdict
import json

TIMESTAMP = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
CSV_PATH = f"iam_users_{TIMESTAMP}.csv"
XLSX_PATH = f"iam_users_{TIMESTAMP}.xlsx"

session = boto3.Session()
iam = session.client("iam")
sts = session.client("sts")

def safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except botocore.exceptions.ClientError as e:
        return {"_error": e.response.get("Error", {}).get("Message", str(e))}
    except Exception as e:
        return {"_error": str(e)}

def list_all_users():
    users = []
    paginator = iam.get_paginator("list_users")
    for page in paginator.paginate():
        users.extend(page.get("Users", []))
    return users

def list_groups_for_user(username):
    resp = safe_call(iam.list_groups_for_user, UserName=username)
    if isinstance(resp, dict) and resp.get("_error"):
        return []
    return [g.get("GroupName") for g in resp.get("Groups", [])]

def list_attached_user_policies(username):
    out = []
    paginator = iam.get_paginator("list_attached_user_policies")
    try:
        for page in paginator.paginate(UserName=username):
            for p in page.get("AttachedPolicies", []):
                out.append({"PolicyName": p.get("PolicyName"), "PolicyArn": p.get("PolicyArn")})
    except botocore.exceptions.ClientError:
        pass
    return out

def list_inline_user_policies(username):
    out = []
    paginator = iam.get_paginator("list_user_policies")
    try:
        for page in paginator.paginate(UserName=username):
            for pname in page.get("PolicyNames", []):
                # fetch the inline policy document (URL-encoded JSON)
                try:
                    pol = iam.get_user_policy(UserName=username, PolicyName=pname)
                    # PolicyDocument is a dict (may contain AWS-specific URL-encoded chars)
                    out.append({"PolicyName": pname, "PolicyDocument": pol.get("PolicyDocument")})
                except botocore.exceptions.ClientError:
                    out.append({"PolicyName": pname, "PolicyDocument": None})
    except botocore.exceptions.ClientError:
        pass
    return out

def list_access_keys(username):
    keys = []
    paginator = iam.get_paginator("list_access_keys")
    try:
        for page in paginator.paginate(UserName=username):
            for k in page.get("AccessKeyMetadata", []):
                key_id = k.get("AccessKeyId")
                create_date = k.get("CreateDate")
                status = k.get("Status")
                # Last used info (best-effort)
                last_used = safe_call(iam.get_access_key_last_used, AccessKeyId=key_id)
                if isinstance(last_used, dict) and last_used.get("_error"):
                    lu = None
                else:
                    lu = last_used.get("AccessKeyLastUsed")
                keys.append({
                    "UserName": username,
                    "AccessKeyId": key_id,
                    "Status": status,
                    "CreateDate": create_date,
                    "LastUsed": lu
                })
    except botocore.exceptions.ClientError:
        pass
    return keys

def list_mfa_devices(username):
    out = []
    try:
        resp = iam.list_mfa_devices(UserName=username)
        for m in resp.get("MFADevices", []):
            out.append({"SerialNumber": m.get("SerialNumber"), "EnableDate": m.get("EnableDate")})
    except botocore.exceptions.ClientError:
        pass
    return out

def list_ssh_public_keys(username):
    out = []
    paginator = iam.get_paginator("list_ssh_public_keys")
    try:
        for page in paginator.paginate(UserName=username):
            for s in page.get("SSHPublicKeys", []):
                out.append({
                    "UserName": username,
                    "SSHPublicKeyId": s.get("SSHPublicKeyId"),
                    "Status": s.get("Status"),
                    "UploadDate": s.get("UploadDate")
                })
    except botocore.exceptions.ClientError:
        pass
    return out

def list_user_tags(username):
    try:
        resp = iam.list_user_tags(UserName=username)
        return {t["Key"]: t["Value"] for t in resp.get("Tags", [])}
    except botocore.exceptions.ClientError:
        return {}

def gather_user_record(user):
    username = user.get("UserName")
    user_id = user.get("UserId")
    arn = user.get("Arn")
    path = user.get("Path")
    create_date = user.get("CreateDate")
    password_last_used = user.get("PasswordLastUsed")  # may be absent
    # Groups
    groups = list_groups_for_user(username)
    # Managed policies
    managed_policies = list_attached_user_policies(username)
    # Inline policies
    inline_policies = list_inline_user_policies(username)
    # Access keys
    access_keys = list_access_keys(username)
    # MFA
    mfa = list_mfa_devices(username)
    # SSH public keys
    ssh_keys = list_ssh_public_keys(username)
    # Tags
    tags = list_user_tags(username)

    # Build a flattened user dict for tabular output
    user_row = {
        "UserName": username,
        "UserId": user_id,
        "Arn": arn,
        "Path": path,
        "CreateDate": create_date,
        "PasswordLastUsed": password_last_used,
        "Groups": ", ".join(groups) if groups else None,
        "ManagedPolicies": ", ".join([p["PolicyName"] for p in managed_policies]) if managed_policies else None,
        "InlinePolicies": ", ".join([p["PolicyName"] for p in inline_policies]) if inline_policies else None,
        "AccessKeyCount": len(access_keys),
        "MFADevicesCount": len(mfa),
        "SSHPublicKeysCount": len(ssh_keys),
    }

    # Add tags as tag_<Key> columns
    for k, v in tags.items():
        user_row[f"tag_{k}"] = v

    # Also keep the full objects (for JSON or detailed sheets)
    details = {
        "ManagedPolicies": managed_policies,
        "InlinePolicies": inline_policies,
        "AccessKeys": access_keys,
        "MFADevices": mfa,
        "SSHPublicKeys": ssh_keys,
        "Tags": tags
    }

    return user_row, details

def main():
    caller = sts.get_caller_identity()
    account = caller.get("Account")
    print(f"Running IAM inventory for account: {account}")

    users = list_all_users()
    print(f"Discovered {len(users)} IAM users")

    rows = []
    access_key_rows = []
    detailed_map = {}

    for u in users:
        user_row, details = gather_user_record(u)
        rows.append(user_row)

        # Collect per-access-key row for separate sheet
        for ak in details.get("AccessKeys", []):
            access_key_rows.append({
                "UserName": ak.get("UserName"),
                "AccessKeyId": ak.get("AccessKeyId"),
                "Status": ak.get("Status"),
                "CreateDate": ak.get("CreateDate"),
                "LastUsedDate": ak.get("LastUsed", {}).get("LastUsedDate") if isinstance(ak.get("LastUsed"), dict) else None,
                "LastUsedRegion": ak.get("LastUsed", {}).get("Region") if isinstance(ak.get("LastUsed"), dict) else None,
                "LastUsedService": ak.get("LastUsed", {}).get("ServiceName") if isinstance(ak.get("LastUsed"), dict) else None,
            })

        # Save full JSON details to a dict keyed by username
        detailed_map[user_row["UserName"]] = details

    df_users = pd.DataFrame(rows)
    df_access = pd.DataFrame(access_key_rows)

    # Save CSV and Excel
    df_users.to_csv(CSV_PATH, index=False)

    with pd.ExcelWriter(XLSX_PATH, engine="openpyxl") as writer:
        df_users.to_excel(writer, sheet_name="Users", index=False)
        if not df_access.empty:
            df_access.to_excel(writer, sheet_name="AccessKeys", index=False)
        # Optionally add a sheet with full JSON dump of details
        # Write a JSON column with pretty-printed details (not required)
        # Build a small df with username + json details
        detail_rows = []
        for uname, det in detailed_map.items():
            detail_rows.append({"UserName": uname, "DetailsJson": json.dumps(det, default=str)})
        df_det = pd.DataFrame(detail_rows)
        df_det.to_excel(writer, sheet_name="UserDetailsJson", index=False)

    print(f"✅ Wrote:\n - {CSV_PATH}\n - {XLSX_PATH}")
    print(f"Users: {len(df_users)}, AccessKeys rows: {len(df_access)}")

if __name__ == "__main__":
    main()
