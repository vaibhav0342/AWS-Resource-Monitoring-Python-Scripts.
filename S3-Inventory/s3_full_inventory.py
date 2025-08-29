#!/usr/bin/env python3
"""
***************************** VAIBHAV UPARE ******************************
python3  s3_full_inventory.py
Produce S3 inventory of all buckets + per-bucket metadata (region, encryption, versioning, lifecycle, ACL/public)
python3 --version
aws configure     Enter AWS Access Key, Secret Key, and default region.
pip install boto3 pandas openpyxl

Outputs:
  - s3_objects_<timestamp>.csv   (all objects)
  - s3_inventory_<timestamp>.xlsx (sheet: Buckets, sheet: Objects)
Notes:
  - Gracefully handles permissions/empty configs and continues.
"""

import boto3
import botocore
import pandas as pd
from datetime import datetime
from collections import defaultdict
import traceback

TIMESTAMP = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
OBJECTS_CSV = f"s3_objects_{TIMESTAMP}.csv"
WORKBOOK_XLSX = f"s3_inventory_{TIMESTAMP}.xlsx"

session = boto3.Session()  # will pick up env/profile/role
s3 = session.client("s3")
s3res = session.resource("s3")

def safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except botocore.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        return {"_error": str(e), "_code": code}
    except Exception as e:
        return {"_error": str(e)}

def get_bucket_region(bucket_name):
    resp = safe_call(s3.get_bucket_location, Bucket=bucket_name)
    if isinstance(resp, dict) and resp.get("_error"):
        return None, resp
    # LocationConstraint can be None for us-east-1
    loc = resp.get("LocationConstraint")
    if loc is None:
        return "us-east-1", None
    # Some regions return like 'EU' for eu-west-1 historically; handle gracefully
    return loc, None

def get_bucket_encryption(bucket_name):
    resp = safe_call(s3.get_bucket_encryption, Bucket=bucket_name)
    if isinstance(resp, dict) and resp.get("_error"):
        return None, resp
    rules = resp.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
    # Simplify: return list of algorithms and kms keys if present
    algos = []
    for r in rules:
        apply = r.get("ApplyServerSideEncryptionByDefault", {})
        algo = apply.get("SSEAlgorithm")
        kms = apply.get("KMSMasterKeyID")
        algos.append({"Algorithm": algo, "KMSKeyId": kms})
    return algos or None, None

def get_bucket_versioning(bucket_name):
    resp = safe_call(s3.get_bucket_versioning, Bucket=bucket_name)
    if isinstance(resp, dict) and resp.get("_error"):
        return None, resp
    # resp may contain Status: Enabled | Suspended and MFADelete
    return resp, None

def get_bucket_lifecycle(bucket_name):
    resp = safe_call(s3.get_bucket_lifecycle_configuration, Bucket=bucket_name)
    if isinstance(resp, dict) and resp.get("_error"):
        # If no lifecycle -> error code NoSuchLifecycleConfiguration usually
        return None, resp
    return resp.get("Rules", []), None

def get_bucket_acl(bucket_name):
    resp = safe_call(s3.get_bucket_acl, Bucket=bucket_name)
    if isinstance(resp, dict) and resp.get("_error"):
        return None, resp
    # Basic analysis: is any grant to AllUsers / AuthenticatedUsers
    public = False
    grants = resp.get("Grants", [])
    for g in grants:
        gr = g.get("Grantee", {})
        uri = gr.get("URI")
        if uri and ("AllUsers" in uri or "AuthenticatedUsers" in uri):
            public = True
            break
    return {"Grants": grants, "Owner": resp.get("Owner"), "Public": public}, None

def get_bucket_policy_status(bucket_name):
    resp = safe_call(s3.get_bucket_policy_status, Bucket=bucket_name)
    if isinstance(resp, dict) and resp.get("_error"):
        return None, resp
    return resp.get("PolicyStatus"), None

def get_public_access_block(bucket_name):
    resp = safe_call(s3.get_public_access_block, Bucket=bucket_name)
    if isinstance(resp, dict) and resp.get("_error"):
        return None, resp
    return resp.get("PublicAccessBlockConfiguration"), None

def get_object_lock_config(bucket_name):
    resp = safe_call(s3.get_object_lock_configuration, Bucket=bucket_name)
    if isinstance(resp, dict) and resp.get("_error"):
        return None, resp
    return resp.get("ObjectLockConfiguration"), None

def list_all_objects(bucket_name):
    paginator = s3.get_paginator("list_objects_v2")
    page_iter = paginator.paginate(Bucket=bucket_name)
    for page in page_iter:
        for obj in page.get("Contents", []):
            yield obj

def object_has_sse(bucket_name, key):
    # We will attempt a head_object to read SSE headers - this is best-effort and may be S3:GetObject required
    try:
        hd = s3.head_object(Bucket=bucket_name, Key=key)
        sse = {
            "SSEAlgorithm": hd.get("ServerSideEncryption"),
            "SSEKMSKeyId": hd.get("SSEKMSKeyId"),
            "SSECustomerAlgorithm": hd.get("SSECustomerAlgorithm")
        }
        return sse, None
    except botocore.exceptions.ClientError as e:
        return None, {"_error": str(e)}
    except Exception as e:
        return None, {"_error": str(e)}

def summarize_bucket_objects(bucket_name):
    total_bytes = 0
    total_objects = 0
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get("Contents", []):
                total_objects += 1
                total_bytes += obj.get("Size", 0)
        return {"TotalObjects": total_objects, "TotalBytes": total_bytes}, None
    except Exception as e:
        return None, {"_error": str(e)}

def main():
    try:
        all_buckets_resp = s3.list_buckets()
    except Exception as e:
        print("ERROR listing buckets:", e)
        return

    buckets = all_buckets_resp.get("Buckets", [])
    bucket_rows = []
    object_rows = []

    for b in buckets:
        name = b["Name"]
        created = b.get("CreationDate")
        print(f"Processing bucket: {name}")

        region, err = get_bucket_region(name)
        if err:
            # try to continue
            print(f"  Warning: region lookup failed: {err}")

        enc, enc_err = get_bucket_encryption(name)
        if enc_err:
            # common: server side encryption configuration not found or access denied
            enc = None

        ver, ver_err = get_bucket_versioning(name)
        if ver_err:
            ver = None

        life, life_err = get_bucket_lifecycle(name)
        if life_err:
            life = None

        acl, acl_err = get_bucket_acl(name)
        if acl_err:
            acl = None

        policy_status, policy_err = get_bucket_policy_status(name)
        if policy_err:
            policy_status = None

        pab, pab_err = get_public_access_block(name)
        if pab_err:
            pab = None

        lock_cfg, lock_err = get_object_lock_config(name)
        if lock_err:
            lock_cfg = None

        summary, sum_err = summarize_bucket_objects(name)
        if sum_err:
            summary = {"TotalObjects": None, "TotalBytes": None}

        bucket_rows.append({
            "BucketName": name,
            "CreationDate": created,
            "Region": region,
            "Encryption": enc,
            "Versioning": ver,
            "LifecycleRules": life,
            "ACL": acl,
            "PolicyStatus": policy_status,
            "PublicAccessBlock": pab,
            "ObjectLockConfiguration": lock_cfg,
            "TotalObjects": summary.get("TotalObjects"),
            "TotalBytes": summary.get("TotalBytes"),
        })

        # Iterate objects (first N optionally to limit)
        # If you want to limit, set a cutoff like max_objects_per_bucket
        max_objects_per_bucket = None  # set to an int to limit for testing
        obj_count = 0
        for obj in list_all_objects(name):
            key = obj.get("Key")
            size = obj.get("Size")
            lastmod = obj.get("LastModified")
            storage = obj.get("StorageClass", "STANDARD")
            etag = obj.get("ETag")
            # Try to get SSE info (best-effort)
            sse, sse_err = object_has_sse(name, key)
            sse_info = sse if sse else (sse_err or None)

            object_rows.append({
                "BucketName": name,
                "Key": key,
                "SizeBytes": size,
                "SizeMB": round(size / (1024*1024), 4) if size is not None else None,
                "LastModified": lastmod,
                "StorageClass": storage,
                "ETag": etag,
                "SSE": sse_info,
            })

            obj_count += 1
            if max_objects_per_bucket and obj_count >= max_objects_per_bucket:
                break

    # Build DataFrames
    df_buckets = pd.DataFrame(bucket_rows)
    df_objects = pd.DataFrame(object_rows)

    # Save CSV for objects (easy large-file)
    df_objects.to_csv(OBJECTS_CSV, index=False)

    # Save Excel with two sheets
    with pd.ExcelWriter(WORKBOOK_XLSX, engine="openpyxl") as writer:
        df_buckets.to_excel(writer, sheet_name="Buckets", index=False)
        df_objects.to_excel(writer, sheet_name="Objects", index=False)

    print(f"\nDone. Wrote:\n - {OBJECTS_CSV}\n - {WORKBOOK_XLSX}")
    print(f"Buckets scanned: {len(df_buckets)}, Objects rows: {len(df_objects)}")

if __name__ == "__main__":
    main()
