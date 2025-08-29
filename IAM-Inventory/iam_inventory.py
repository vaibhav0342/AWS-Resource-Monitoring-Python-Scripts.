#!/usr/bin/env python3
"""
*************************************** VAIBHAV UPARE *********************************
IAM_inventory.py
Inventory all IAM details.
python3 --version
aws configure
pip install boto3 pandas openpyxl
python3 iam_inventory.py
"""

import boto3
import pandas as pd
import json
from datetime import datetime

session = boto3.Session()
iam = session.client("iam")
sts = session.client("sts")

# Get account ID
account_id = sts.get_caller_identity()["Account"]

# ========== Account Info ==========
def get_account_summary():
    summary = iam.get_account_summary()["SummaryMap"]
    try:
        policy = iam.get_account_password_policy()["PasswordPolicy"]
    except iam.exceptions.NoSuchEntityException:
        policy = {}

    return {
        "AccountId": account_id,
        "RootMFAEnabled": summary.get("AccountMFAEnabled"),
        "Users": summary.get("Users", 0),
        "Groups": summary.get("Groups", 0),
        "Roles": summary.get("Roles", 0),
        "Policies": summary.get("Policies", 0),
        "PasswordPolicy": json.dumps(policy)
    }

# ========== Users ==========
def list_users():
    users_data, access_keys_data = [], []
    paginator = iam.get_paginator("list_users")

    for page in paginator.paginate():
        for user in page["Users"]:
            username = user["UserName"]

            # Groups
            groups = [g["GroupName"] for g in iam.list_groups_for_user(UserName=username)["Groups"]]

            # Managed policies
            mpols = [p["PolicyName"] for p in iam.list_attached_user_policies(UserName=username)["AttachedPolicies"]]

            # Inline policies
            ipols = iam.list_user_policies(UserName=username)["PolicyNames"]

            # Access keys
            keys = iam.list_access_keys(UserName=username)["AccessKeyMetadata"]
            for k in keys:
                last_used = iam.get_access_key_last_used(AccessKeyId=k["AccessKeyId"])["AccessKeyLastUsed"]
                access_keys_data.append({
                    "UserName": username,
                    "AccessKeyId": k["AccessKeyId"],
                    "Status": k["Status"],
                    "CreateDate": k["CreateDate"],
                    "LastUsedDate": last_used.get("LastUsedDate"),
                    "LastUsedRegion": last_used.get("Region"),
                    "LastUsedService": last_used.get("ServiceName")
                })

            users_data.append({
                "UserName": username,
                "Arn": user["Arn"],
                "CreateDate": user["CreateDate"],
                "Groups": groups,
                "ManagedPolicies": mpols,
                "InlinePolicies": ipols
            })

    return users_data, access_keys_data

# ========== Groups ==========
def list_groups():
    groups_data = []
    paginator = iam.get_paginator("list_groups")

    for page in paginator.paginate():
        for g in page["Groups"]:
            gp = g["GroupName"]

            # Managed policies
            mpols = [p["PolicyName"] for p in iam.list_attached_group_policies(GroupName=gp)["AttachedPolicies"]]

            # Inline
            ipols = iam.list_group_policies(GroupName=gp)["PolicyNames"]

            groups_data.append({
                "GroupName": gp,
                "Arn": g["Arn"],
                "CreateDate": g["CreateDate"],
                "ManagedPolicies": mpols,
                "InlinePolicies": ipols
            })
    return groups_data

# ========== Roles ==========
def list_roles():
    roles_data = []
    paginator = iam.get_paginator("list_roles")

    for page in paginator.paginate():
        for r in page["Roles"]:
            rname = r["RoleName"]

            mpols = [p["PolicyName"] for p in iam.list_attached_role_policies(RoleName=rname)["AttachedPolicies"]]
            ipols = iam.list_role_policies(RoleName=rname)["PolicyNames"]

            roles_data.append({
                "RoleName": rname,
                "Arn": r["Arn"],
                "CreateDate": r["CreateDate"],
                "AssumeRolePolicy": json.dumps(r["AssumeRolePolicyDocument"]),
                "ManagedPolicies": mpols,
                "InlinePolicies": ipols
            })
    return roles_data

# ========== Policies ==========
def list_policies():
    policies_data = []
    paginator = iam.get_paginator("list_policies")

    for page in paginator.paginate(Scope="All", OnlyAttached=False):
        for p in page["Policies"]:
            policies_data.append({
                "PolicyName": p["PolicyName"],
                "Arn": p["Arn"],
                "Path": p["Path"],
                "DefaultVersionId": p["DefaultVersionId"],
                "AttachmentCount": p["AttachmentCount"],
                "IsAWSManaged": p["Arn"].startswith("arn:aws:iam::aws:policy/"),
                "CreateDate": p["CreateDate"]
            })
    return policies_data

# ========== Main ==========
def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    account_summary = [get_account_summary()]
    users, keys = list_users()
    groups = list_groups()
    roles = list_roles()
    policies = list_policies()

    # Save to Excel
    with pd.ExcelWriter(f"iam_inventory_{timestamp}.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(account_summary).to_excel(writer, sheet_name="AccountSummary", index=False)
        pd.DataFrame(users).to_excel(writer, sheet_name="Users", index=False)
        pd.DataFrame(keys).to_excel(writer, sheet_name="AccessKeys", index=False)
        pd.DataFrame(groups).to_excel(writer, sheet_name="Groups", index=False)
        pd.DataFrame(roles).to_excel(writer, sheet_name="Roles", index=False)
        pd.DataFrame(policies).to_excel(writer, sheet_name="Policies", index=False)

    print(f"✅ IAM Inventory saved: iam_inventory_{timestamp}.xlsx")

if __name__ == "__main__":
    main()
