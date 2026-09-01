import os
import socket
import json
import httpx
from dotenv import load_dotenv

load_dotenv("Backend/.env")

print("=" * 65)
print("  CIRA FULL API & CONNECTION DIAGNOSTIC SUITE")
print("=" * 65)

# 1. OpenRouter LLM API
api_key = os.getenv("OPENROUTER_API_KEY", "")
print("\n[1] Testing OpenRouter AI API...")
if api_key:
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                print(f"    [OK] OpenRouter API Status: 200 OK")
                print(f"    Key Label: {data.get('label', 'Default')}")
                print(f"    Usage Limit: {data.get('limit', 'No limit')}, Usage: {data.get('usage', 0)}")
            else:
                print(f"    [FAIL] OpenRouter API returned HTTP {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        print(f"    [FAIL] OpenRouter connection error: {e}")
else:
    print("    [WARN] No OPENROUTER_API_KEY set in .env")

# 2. Local Backend (FastAPI)
print("\n[2] Testing Local Backend (http://127.0.0.1:8000)...")
try:
    with httpx.Client(timeout=4.0) as client:
        resp = client.get("http://127.0.0.1:8000/health")
        if resp.status_code == 200:
            print(f"    [OK] Local Backend /health is UP! (HTTP 200)")
            print(f"    Response: {json.dumps(resp.json())}")
        else:
            print(f"    [FAIL] Local Backend returned HTTP {resp.status_code}")
except Exception as e:
    print(f"    [INFO] Local Backend (port 8000) is NOT running right now on this machine ({e.__class__.__name__})")

# 3. SAP HANA Port (TCP 30013)
hana_host = os.getenv("HANA_HOST", "20.204.5.237")
hana_port = int(os.getenv("HANA_PORT", "30013"))
print(f"\n[3] Testing SAP HANA Direct DB Connection ({hana_host}:{hana_port})...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(4.0)
    res = sock.connect_ex((hana_host, hana_port))
    if res == 0:
        print(f"    [OK] SAP HANA port {hana_port} is OPEN and REACHABLE!")
    else:
        print(f"    [FAIL] SAP HANA port {hana_port} is UNREACHABLE from this machine (Socket Error: {res})")
        print("    -> Note: Azure firewall blocks incoming traffic from public internet; must run on RDP/VPN.")
    sock.close()
except Exception as e:
    print(f"    [FAIL] SAP HANA socket test error: {e}")

# 4. SAP Service Layer (Port 50000 / HTTPS)
sl_host = os.getenv("SAP_B1_HOST", "20.204.5.237")
sl_port = os.getenv("SAP_B1_PORT", "50000")
print(f"\n[4] Testing SAP Service Layer ({sl_host}:{sl_port})...")
try:
    with httpx.Client(verify=False, timeout=4.0) as client:
        resp = client.get(f"https://{sl_host}:{sl_port}/b1s/v1/")
        print(f"    [OK] Service Layer HTTP Status: {resp.status_code}")
except Exception as e:
    print(f"    [FAIL] Service Layer unreachable from this machine: {e.__class__.__name__}")
    print("    -> Note: Azure firewall blocks incoming traffic from public internet; must run on RDP/VPN.")

print("\n" + "=" * 65)
