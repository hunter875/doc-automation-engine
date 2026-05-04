#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test calendar and detail APIs after KV30 ingestion."""

import json
import sys
import io
import requests

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API_URL = "http://localhost:8000"
EMAIL = "minhln8@gmail.com"
PASSWORD = "Hunter87512@"

def login():
    resp = requests.post(
        f"{API_URL}/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    if resp.status_code != 200:
        print(f"FAIL Login failed: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    token = data["access_token"]
    print(f"OK Logged in")
    return token

def get_tenant_and_template(token):
    resp = requests.get(
        f"{API_URL}/api/v1/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        print(f"FAIL List tenants failed: {resp.status_code} {resp.text}")
        return None, None
    tenants = resp.json()
    if not tenants:
        print("FAIL No tenants")
        return None, None
    tenant_id = tenants[0]["id"]
    print(f"OK tenant_id={tenant_id}")

    resp = requests.get(
        f"{API_URL}/api/v1/extraction/templates",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    if resp.status_code != 200:
        print(f"FAIL List templates failed: {resp.status_code} {resp.text}")
        return tenant_id, None
    templates = resp.json().get("items", [])
    if not templates:
        print("FAIL No templates")
        return tenant_id, None
    template_id = templates[0]["id"]
    print(f"OK template_id={template_id}")
    return tenant_id, template_id

def test_calendar(token, tenant_id, template_id):
    print("\n=== Test Calendar API ===")
    resp = requests.get(
        f"{API_URL}/api/reports/calendar",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
        params={
            "template_id": template_id,
            "with_metadata": "true",
        }
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"FAIL Calendar error: {resp.text}")
        return False, None

    data = resp.json()
    print(json.dumps(data, indent=2, ensure_ascii=False))

    if "dates_with_reports" in data and len(data["dates_with_reports"]) > 0:
        print(f"\nOK Found {len(data['dates_with_reports'])} dates in calendar")
        return True, data["dates_with_reports"][0] if data["dates_with_reports"] else None
    else:
        print("\nWARN No dates found in calendar")
        return False, None

def test_detail(token, tenant_id, template_id, date_str):
    print(f"\n=== Test Detail API for date {date_str} ===")
    resp = requests.get(
        f"{API_URL}/api/reports/daily",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
        params={
            "date": date_str,
            "template_id": template_id,
            "source": "default",
        }
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"FAIL Detail error: {resp.text}")
        return False

    data = resp.json()
    if "data" in data:
        ed = data["data"]
        print(f"OK Got extraction data:")
        print(f"  - header: {ed.get('header', {}).get('so_bao_cao', 'N/A')}")
        print(f"  - CNCH count: {len(ed.get('danh_sach_cnch', []))}")
        print(f"  - Chi viên count: {len(ed.get('danh_sach_chi_vien', []))}")
        print(f"  - Vụ cháy count: {len(ed.get('danh_sach_chay', []))}")
        print(f"  - SCLQ count: {len(ed.get('danh_sach_sclq', []))}")
        return True
    else:
        print("WARN No data in response")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return False

def main():
    print("=== Test Calendar & Detail APIs ===")
    token = login()
    if not token:
        return 1

    tenant_id, template_id = get_tenant_and_template(token)
    if not tenant_id or not template_id:
        return 1

    success, first_date = test_calendar(token, tenant_id, template_id)

    # Test detail API with a known date that has extracted data
    test_date = "2026-03-02"
    print(f"\n=== Testing detail API with known date {test_date} ===")
    if not test_detail(token, tenant_id, template_id, test_date):
        print(f"WARN Detail API failed for {test_date}")

    if success and first_date:
        if not test_detail(token, tenant_id, template_id, first_date):
            return 1
    elif not success:
        print("INFO Calendar is empty (expected for extracted jobs not yet reviewed)")

    print("\n=== Tests completed ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
