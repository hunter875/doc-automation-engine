#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import requests
import json

# Force UTF-8 output
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_URL = "http://localhost:8000"
EMAIL = "minhln8@gmail.com"
PASSWORD = "Hunter87512@"

def login():
    resp = requests.post(f"{API_URL}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if resp.status_code != 200:
        print(f"FAIL Login: {resp.text}")
        return None
    return resp.json()["access_token"]

def get_tenant_and_template(token):
    resp = requests.get(f"{API_URL}/api/v1/tenants", headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        print(f"FAIL Tenants: {resp.text}")
        return None, None
    tenant_id = resp.json()[0]["id"]
    
    resp = requests.get(f"{API_URL}/api/v1/extraction/templates", headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id})
    if resp.status_code != 200:
        print(f"FAIL Templates: {resp.text}")
        return tenant_id, None
    templates = resp.json().get("items", [])
    template_id = templates[0]["id"]
    return tenant_id, template_id

def test_detail(token, tenant_id, template_id, date_str):
    print(f"\n=== Test Detail API for date {date_str} ===")
    resp = requests.get(
        f"{API_URL}/api/reports/daily",
        params={"date": date_str, "template_id": template_id},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"FAIL Detail error: {resp.text}")
        return False
    
    data = resp.json()
    print("OK Got extraction data:")
    print(f"  job_id: {data.get('job_id', 'N/A')}")
    print(f"  version: {data.get('version', 'N/A')}")
    print(f"  status: {data.get('status', 'N/A')}")
    print(f"  review_status: {data.get('review_status', 'N/A')}")
    
    ed = data.get("data", {})
    header = ed.get("header", {})
    print("\nHeader:")
    print(f"  so_bao_cao: {header.get('so_bao_cao', '')}")
    print(f"  ngay_bao_cao: {header.get('ngay_bao_cao', '')}")
    print(f"  don_vi_bao_cao: {header.get('don_vi_bao_cao', '')}")
    print(f"  thoi_gian_tu_den: {header.get('thoi_gian_tu_den', '')}")
    
    print("\nDetail sections:")
    print(f"  - CNCH count: {len(ed.get('danh_sach_cnch', []))}")
    print(f"  - Chi vien count: {len(ed.get('danh_sach_chi_vien', []))}")
    print(f"  - Vu chay count: {len(ed.get('danh_sach_chay', []))}")
    print(f"  - SCLQ count: {len(ed.get('danh_sach_sclq', []))}")
    
    # Print first item of each non-empty list
    for section_name in ['danh_sach_cnch', 'danh_sach_chi_vien', 'danh_sach_chay', 'danh_sach_sclq']:
        items = ed.get(section_name, [])
        if items:
            print(f"\nFirst item of {section_name}:")
            print(f"  {json.dumps(items[0], ensure_ascii=False, indent=2)}")
    
    return True

def main():
    print("=== Test Detail API for Rich Dates ===")
    token = login()
    if not token:
        return 1
    print("OK Logged in")
    
    tenant_id, template_id = get_tenant_and_template(token)
    if not tenant_id or not template_id:
        return 1
    print(f"OK tenant_id={tenant_id}")
    print(f"OK template_id={template_id}")
    
    # Test rich dates
    for date_str in ["2026-04-10", "2026-03-21", "2026-03-31"]:
        test_detail(token, tenant_id, template_id, date_str)
    
    print("\n=== Tests completed ===")
    return 0

if __name__ == "__main__":
    exit(main())
