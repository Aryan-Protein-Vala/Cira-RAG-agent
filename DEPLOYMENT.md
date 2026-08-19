# CIRA — Deployment runbook (Windows RDP / company server)

Every command below is copy-paste ready. Adjust `C:\CIRA` if you unzip somewhere else.

Prerequisites on the box:
- **Python 3.11+** (`python --version`)
- **Node.js 20.9+ or 22 LTS** (`node -v`) — Next.js 16 will not run on Node 18
- The HANA SQL port (30013 / 3xx15) and/or Service Layer (50000) reachable **from this machine**

---

## 1. Unzip and check the tools

```bat
cd C:\
mkdir CIRA
:: extract the zip into C:\CIRA so that C:\CIRA\Backend and C:\CIRA\Frontend exist

cd C:\CIRA
dir
python --version
node -v
npm -v
```

---

## 2. Backend — install

```bat
cd C:\CIRA\Backend

python -m venv .venv
.venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Backend — configure

```bat
cd C:\CIRA\Backend
copy .env.example .env
notepad .env
```

Fill in at minimum:

```ini
CIRA_DATA_SOURCE=auto

HANA_HOST=20.204.5.237
HANA_PORT=30013
HANA_USER=<read-only user>
HANA_PASSWORD=<password>
HANA_SCHEMA=CIRA_DEMO_NEW
HANA_ENCRYPT=true
HANA_SSL_VALIDATE_CERT=false

SAP_B1_HOST=20.204.5.237
SAP_B1_PORT=50000
SAP_B1_COMPANY_DB=CIRA_DEMO_NEW
SAP_B1_USER=manager
SAP_B1_PASSWORD=<password>

OPENROUTER_API_KEY=<key>
CIRA_MODEL=openrouter/free

CIRA_SECRET_KEY=<paste the generated value from step 4>
CIRA_ALLOW_ANY_EMPLOYEE=true
CIRA_ALLOWED_ORIGINS=
```

## 4. Generate a session secret (do this once, paste into .env)

```bat
cd C:\CIRA\Backend
.venv\Scripts\python -c "import secrets;print(secrets.token_urlsafe(48))"
```

## 5. Migrate the chat DB and prove the SAP connection

```bat
cd C:\CIRA\Backend
.venv\Scripts\python migrate_db.py --check
```

Read the output. You want:

```
Active backend : SAP HANA
Simulated      : False
Tables visible : 700+
```

If it says `SAP B1 Simulator` / `Simulated : True`, **you are not on live data**. Diagnose:

```bat
cd C:\CIRA\Backend
.venv\Scripts\python -c "import socket;socket.create_connection(('20.204.5.237',30013),5);print('SQL port OPEN')"
.venv\Scripts\python -c "import socket;socket.create_connection(('20.204.5.237',50000),5);print('Service Layer OPEN')"
```

- port closed → firewall / NSG, or wrong port (try the tenant port `30015`)
- port open but login fails → wrong user/password, or try `HANA_ENCRYPT=false`
- connects but schema missing → wrong `HANA_SCHEMA`; the log prints the schemas that contain `OADM`

## 6. Backend — run

```bat
cd C:\CIRA\Backend
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Bind to `127.0.0.1`, not `0.0.0.0`: the API should only be reachable through the web app / reverse
proxy, never directly from the network.

Smoke test in a **second** window:

```powershell
cd C:\CIRA
Invoke-RestMethod http://127.0.0.1:8000/health
$t = (Invoke-RestMethod -Method Post http://127.0.0.1:8000/auth/login -ContentType application/json -Body '{"employee_id":"admin","password":"asdfghjkl;"}').token
Invoke-RestMethod http://127.0.0.1:8000/sap/health -Headers @{Authorization="Bearer $t"} | ConvertTo-Json -Depth 4
```

---

## 7. Frontend — install, build, run

```bat
cd C:\CIRA\Frontend
npm install
npm run build
npm start
```

`npm start` serves on port 3000 and proxies `/api/*` to `http://127.0.0.1:8000` (default
`BACKEND_ORIGIN`). If the backend runs on another machine or port:

```bat
cd C:\CIRA\Frontend
set BACKEND_ORIGIN=http://10.0.0.5:8000
npm run build
npm start
```

Test locally on the server: open `http://localhost:3000`, sign in with `admin` / `asdfghjkl;`,
ask *"Show me all open invoices from last quarter"*. The header pill must say **Live SAP**, not
*Sandbox data*.

---

## 8. Keep both running as Windows services (NSSM)

Two console windows die when you log off RDP. Install [NSSM](https://nssm.cc/download), unzip to
`C:\nssm`, then:

```bat
cd C:\nssm\win64

nssm install CIRA-API "C:\CIRA\Backend\.venv\Scripts\python.exe" "-m uvicorn main:app --host 127.0.0.1 --port 8000"
nssm set CIRA-API AppDirectory C:\CIRA\Backend
nssm set CIRA-API AppStdout C:\CIRA\logs\api.log
nssm set CIRA-API AppStderr C:\CIRA\logs\api.err.log
nssm set CIRA-API Start SERVICE_AUTO_START

nssm install CIRA-WEB "C:\Program Files\nodejs\npm.cmd" "start"
nssm set CIRA-WEB AppDirectory C:\CIRA\Frontend
nssm set CIRA-WEB AppStdout C:\CIRA\logs\web.log
nssm set CIRA-WEB AppStderr C:\CIRA\logs\web.err.log
nssm set CIRA-WEB Start SERVICE_AUTO_START

mkdir C:\CIRA\logs
nssm start CIRA-API
nssm start CIRA-WEB
```

Manage them later:

```bat
cd C:\nssm\win64
nssm restart CIRA-API
nssm restart CIRA-WEB
nssm status CIRA-API
```

---

## 9. Updating after a code change

```bat
cd C:\CIRA\Backend
.venv\Scripts\activate
pip install -r requirements.txt
python migrate_db.py

cd C:\CIRA\Frontend
npm install
npm run build

cd C:\nssm\win64
nssm restart CIRA-API
nssm restart CIRA-WEB
```

---

## 10. Exposing it to external users (HTTPS)

**Do not** open port 3000 or 8000 to the internet directly. Put a reverse proxy with a real
certificate in front, and only expose 443.

Before you expose anything, change these in `Backend\.env`:

```ini
CIRA_ALLOW_ANY_EMPLOYEE=false          # demo mode: today ANY id + ANY password gets in
CIRA_SECRET_KEY=<a long random value>
CIRA_ALLOWED_ORIGINS=https://cira.yourdomain.com
CIRA_TOKEN_TTL_SECONDS=28800
```

### Option A — Caddy (simplest, automatic Let's Encrypt)

`C:\CIRA\Caddyfile`:

```
cira.yourdomain.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:3000 {
        flush_interval -1        # required: never buffer the SSE chat stream
    }
}
```

```bat
cd C:\CIRA
caddy run --config Caddyfile
```

### Option B — nginx

```nginx
server {
    listen 443 ssl;
    server_name cira.yourdomain.com;
    ssl_certificate     C:/certs/fullchain.pem;
    ssl_certificate_key C:/certs/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;        # SSE
        proxy_read_timeout 300s;
    }
}
```

### Option C — IIS + Application Request Routing

If IIS is the company standard: install URL Rewrite + ARR, create a site bound to 443 with the
certificate, add a reverse-proxy rule to `http://127.0.0.1:3000`, and in the ARR proxy settings set
**Response buffer threshold = 0** (otherwise the chat streams nothing until it finishes).

### Firewall

```powershell
New-NetFirewallRule -DisplayName "CIRA HTTPS" -Direction Inbound -LocalPort 443 -Protocol TCP -Action Allow
Get-NetFirewallRule -DisplayName "CIRA*"
```

---

## 11. Troubleshooting cheat-sheet

| Symptom | Check |
|---|---|
| Header pill says *Sandbox data* | `.venv\Scripts\python migrate_db.py --check` — read the probe log |
| Login works, chat says "Cannot reach the CIRA backend" | Is `CIRA-API` running? `Invoke-RestMethod http://127.0.0.1:8000/health` |
| Chat answer appears all at once at the end | Proxy is buffering — `proxy_buffering off` / `flush_interval -1` / ARR buffer threshold 0 |
| "The AI model rejected the request" | `OPENROUTER_API_KEY` missing or out of credit |
| Answers arrive but with no table/chart | The model didn't call a tool — check `C:\CIRA\logs\api.log` for `sap_query` |
| `npm install` fails on a proxy | `npm config set proxy http://user:pass@proxy:8080` (and `https-proxy`) |
| Everything dies when you log off RDP | You're running in a console, not as an NSSM service (step 8) |
