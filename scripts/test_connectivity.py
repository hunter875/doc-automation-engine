#!/usr/bin/env python3
"""Diagnostic script to test Ollama connectivity from container"""

import socket
import sys

print("=" * 60)
print("OLLAMA CONNECTIVITY DIAGNOSTIC")
print("=" * 60)

# Test 1: DNS Resolution
print("\n[1] Testing DNS resolution of 'host.docker.internal'...")
try:
    ip = socket.gethostbyname('host.docker.internal')
    print(f"    ✓ Resolved to: {ip}")
except socket.gaierror as e:
    print(f"    ✗ DNS Failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"    ✗ Unexpected error: {e}")
    sys.exit(1)

# Test 2 TCP Connection
print("\n[2] Testing TCP connection to port 11434...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
try:
    result = sock.connect_ex(('host.docker.internal', 11434))
    if result == 0:
        print(f"    ✓ TCP port 11434 is OPEN")
    else:
        print(f"    ✗ TCP port 11434 is CLOSED (errno {result})")
        sys.exit(2)
except Exception as e:
    print(f"    ✗ TCP test failed: {e}")
    sys.exit(2)
finally:
    sock.close()

# Test 3: HTTP Connectivity
print("\n[3] Testing HTTP endpoint GET /api/ps...")
try:
    import requests
    resp = requests.get('http://host.docker.internal:11434/api/ps', timeout=10)
    print(f"    ✓ HTTP Status: {resp.status_code}")
    data = resp.json()
    models = data.get('models', [])
    print(f"    ✓ Models loaded in memory: {len(models)}")
    for m in models:
        vram = m.get('size_vram')
        if vram:
            print(f"      - {m['name']}: {vram/(1024**3):.1f} GB in VRAM")
        else:
            print(f"      - {m['name']}: Not in VRAM")
except requests.exceptions.Timeout as e:
    print(f"    ✗ HTTP Timeout: {e}")
    print("       (Ollama server is not responding)")
    sys.exit(3)
except requests.exceptions.ConnectionError as e:
    print(f"    ✗ HTTP Connection Error: {e}")
    sys.exit(3)
except Exception as e:
    print(f"    ✗ HTTP test failed: {e}")
    sys.exit(3)

print("\n" + "=" * 60)
print("ALL TESTS PASSED ✓")
print("=" * 60)
