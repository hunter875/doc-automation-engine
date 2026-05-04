#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E test: Ingest Google Sheet via API and verify resolver logs."""

import json
import sys
import time
import requests
import io

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API_URL = "http://localhost:8000"
EMAIL = "minhln8@gmail.com"
PASSWORD = "Hunter87512@"
SHEET_ID = "1vfWhL4ZFRiwlrhjEAlCemE9sPlNHvuxFiT_1hA5NDYI"
SHEET_GID = "1539120052"  # from the URL, the specific tab

def main():
    print("=== E2E Ingestion Test ===")
    print("1. Login...")
    resp = requests.post(
        f"{API_URL}/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    if resp.status_code != 200:
        print(f"FAIL Login failed: {resp.status_code} {resp.text}")
        return 1

    data = resp.json()
    token = data["access_token"]
    print(f"OK Logged in | token={token[:20]}...")

    print("\n2. List tenants...")
    resp = requests.get(
        f"{API_URL}/api/v1/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        print(f"FAIL List tenants failed: {resp.status_code} {resp.text}")
        return 1
    tenants = resp.json()
    if not tenants:
        print("FAIL No tenants available for this user")
        return 1
    tenant_id = tenants[0]["id"]
    print(f"OK tenant_id={tenant_id} | tenant_name={tenants[0].get('name')}")

    print("\n3. List templates...")
    resp = requests.get(
        f"{API_URL}/api/v1/extraction/templates",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    if resp.status_code != 200:
        print(f"FAIL List templates failed: {resp.status_code} {resp.text}")
        return 1
    templates_data = resp.json()
    templates = templates_data.get("items", [])
    if not templates:
        print("FAIL No templates available")
        return 1
    template_id = templates[0]["id"]
    print(f"OK Using template_id={template_id} | name={templates[0].get('name')}")

    print("\n4. Trigger async ingestion (KV30 mode)...")
    payload = {
        "template_id": template_id,
        "sheet_id": SHEET_ID,
        "mode": "kv30",
        # "worksheet_gid": SHEET_GID,  # Commented out for now - requires Google credentials
    }
    print(f"DEBUG payload: {payload}")
    resp = requests.post(
        f"{API_URL}/api/v1/extraction/jobs/ingest/google-sheet",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
        json=payload,
    )
    if resp.status_code not in (200, 202):
        print(f"FAIL Ingestion failed: {resp.status_code} {resp.text}")
        return 1

    data = resp.json()
    task_id = data["task_id"]
    print(f"OK Task enqueued | task_id={task_id}")

    print("\n5. Poll task status (max 60s)...")
    for i in range(1, 21):
        time.sleep(3)
        resp = requests.get(
            f"{API_URL}/api/v1/extraction/jobs/ingest/google-sheet/{task_id}",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
        )
        data = resp.json()
        status = data["status"]
        print(f"  [{i}] status={status}")

        if status == "completed":
            print("\nOK Task completed!")
            summary = data.get("summary", {})
            print(json.dumps(summary, indent=2, ensure_ascii=False))

            # Check for resolver_debug in error case
            if summary.get("status") == "error":
                print("\nWARN Ingestion returned error status.")
                error_msg = summary.get("error", "No error message")
                print(f"Error: {error_msg}")
                resolver_debug = summary.get("resolver_debug", {})
                if resolver_debug:
                    print("\nResolver debug:")
                    print(json.dumps(resolver_debug, indent=2, ensure_ascii=False))
            return 0

        elif status == "failed":
            print("\nFAIL Task failed!")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return 1

    print("\n⏱️ Timeout waiting for task completion")
    return 1

if __name__ == "__main__":
    sys.exit(main())
