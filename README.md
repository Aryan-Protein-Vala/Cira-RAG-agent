# CIRA — Corporate Intelligence & Reporting Assistant

Ask your SAP Business One (HANA) company database anything in plain English and get an
interactive table, a chart and a two-line executive summary back.

```
Frontend (Next.js 16 / React 19)  ──/api/*──►  Backend (FastAPI)  ──►  1. SAP HANA          (SQL, full depth — THE primary source)
      browser only ever talks to Next   │                            2. SAP B1 Service Layer (OData, entity level)
                                        │                            3. SQL Server          (B1 on MS SQL)
                                        └──► 4. Offline sandbox       (dev/CI, always labelled SIMULATED)
```

The four sources are tried in that order by `sap/router.py`; the order is
`CIRA_DATA_SOURCE_ORDER` and is **never** inferred from "some password happened
to be set" (that inference is what made an old build prefer SQL Server over
HANA). A source is enabled when its host + credentials are configured, and
`CIRA_DATA_SOURCE=hana` pins it and fails loudly if HANA is unreachable.

---

## 1. Quick start

### Backend

```bash
cd Backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                         # see the hdbcli note at the top of that file
cp .env.example .env
# Required in .env — the app refuses to start without the first two:
#   HANA_HOST / HANA_USER / HANA_PASSWORD / HANA_SCHEMA
#   CIRA_ALLOWED_ORIGINS=http://localhost:3000           (CIRA_STRICT=true by default)
#   CIRA_ADMIN_ID / CIRA_ADMIN_PASSWORD / CIRA_SECRET_KEY
#   OPENROUTER_API_KEY                                   (optional; else deterministic planner)
python ../scripts/diagnose.py --require-live     # what would actually answer? (exit 1 = not live)
python migrate_db.py --check                     # migrate cira.db + config validation
uvicorn main:app --host 0.0.0.0 --port 8000
```

> **Credentials are never defaults.** `config.py` has no fallback for any
> password, hostname or admin account. An earlier build shipped a live SQL
> Server `sa` password as the default value of `MSSQL_PASSWORD`; that value is
> in git history and **must be rotated**, not just deleted (see §9).

### Frontend

```bash
cd Frontend
npm install
npm run dev            # http://localhost:3000  (proxies /api/* to the backend)
npm run lint           # eslint (flat config); npx tsc --noEmit also passes
# production: npm run build && npm start
```

Sign in with the `CIRA_ADMIN_ID` / `CIRA_ADMIN_PASSWORD` you put in `.env`. There is no
shipped demo account, and `CIRA_ALLOW_ANY_EMPLOYEE` (any ID + any password) defaults to
**false** — enable it only for a throwaway demo.

**Nothing is mandatory to get a running system**: with no HANA reachable and no LLM key,
CIRA boots into the offline SAP B1 sandbox with a deterministic planner and still renders
real tables and charts — clearly labelled `SIMULATED` so nobody mistakes it for production data.

---

## 2. How deep the SAP access goes

The agent has four data tools; together they can reach *any* table, view, user table (`@…`) or
user field (`U_…`) in the company schema:

| Tool | What it does |
|---|---|
| `sap_search_schema(keyword)` | Searches table names, table comments, **column names and column comments** across the whole schema (`SYS.TABLE_COLUMNS`). This is how the agent finds fields it was never told about. |
| `sap_describe_table(table)` | Full column list with types + descriptions, row count and sample rows. Accepts `OINV` or “invoices”. |
| `sap_query(...)` | Structured query: column selection, filters (`eq/ne/gt/gte/lt/lte/contains/startswith/in/between/isnull`), free-text search, date window (`year`, `date_from`, `date_to`), `group_by`, aggregates (`sum/count/avg/min/max/count_distinct`), ordering, row cap. |
| `sap_sql(sql)` | Guarded read-only SELECT for joins, sub-queries, window functions, UNION, HAVING — e.g. revenue per item across `RDR1 ⨝ ORDR`. |

Safety rails (`sap/sql_guard.py`):
* single statement only; `SELECT`/`WITH` only; DDL/DML/`CALL`/locking clauses rejected even inside sub-queries;
* **scoped, not just read-only** — every qualified `FROM`/`JOIN` must sit in the company schema
  (+ `HANA_EXTRA_SCHEMAS`); catalog reads are limited to a metadata allowlist, so
  `SELECT * FROM "SYS"."USERS"` (password hashes, on a SYSTEM connection) is refused;
* identifiers validated against the live catalog and quoted per dialect (`"X"` for HANA,
  `[X]` for SQL Server); values always bound as parameters, re-bound to the driver's
  paramstyle *outside* string literals;
* a row cap is injected in the target dialect (`TOP`/`LIMIT`/`OFFSET…FETCH NEXT`), because
  `LIMIT` is a syntax error in T-SQL.

Business semantics are built in: friendly names (`invoices → OINV`, `vendors → OCRD`,
`journal lines → JDT1`, ~80 aliases), status words translated to B1 codes
(`Open → 'O'`, `vendor → 'S'`) on the way in and back to words on the way out,
per-table “preferred columns” so a 150-column header table doesn’t drown the UI,
and known date/amount/party columns per table for automatic charting.

---

## 3. What was broken, and what changed

### 3.0 Security and correctness pass (v2.1) — what this round fixed

| Problem found in review | Fix |
|---|---|
| A live SQL Server `sa` password, an RDP machine password and the HANA public IP were committed in `config.py` / `start_ssh_tunnel.bat` | No credential/hostname defaults anywhere; `start_ssh_tunnel.bat` reads git-ignored `tunnel.env` and prompts; **rotation still required** (§9.3) |
| `auto` preferred MSSQL and **never tried HANA** unless a password happened to be set | Explicit enablement per source + `CIRA_DATA_SOURCE_ORDER` with HANA first; `CIRA_DATA_SOURCE=hana` fails loudly if unreachable |
| `CIRA_ALLOW_ANY_EMPLOYEE=true` plus a working `admin` password documented in the README and defaulted in `config.py` | Both default off/empty; unknown company DBs rejected at sign-in; generic 401 with no user enumeration |
| `GET /sap/health` was public and dumped host/port/schema/user/Service-Layer URL (a test asserted otherwise and was failing on `main`) | Token required; payload reduced to booleans + counts; tests green |
| `POST /sap/write` was callable by any session on any entity | Disabled unless `CIRA_SAP_WRITE_ENABLED`, admin-role only, entity allowlist, payload bounds, audited; sandbox refuses instead of faking success |
| SQL guard was read-only but **not scoped** (`SELECT * FROM "SYS"."USERS"` passed) | `enforce_scope()` allowlists the company schema (+`HANA_EXTRA_SCHEMAS`) and catalog metadata views, rejects locking clauses |
| Service Layer path skipped catalog validation → OData injection via column names | Every filter/select/order identifier resolved through the live catalog; `safe_odata_name()` on both fields and entity sets |
| Service Layer retry after a 401 dropped `$filter/$select/$top` → silently unfiltered results presented as the filtered answer | Retry repeats the query |
| `apply_row_limit` emitted `LIMIT` for SQL Server (invalid T-SQL) | Dialect-correct caps (`TOP` / `LIMIT` / `OFFSET…FETCH NEXT`) |
| `mssql.execute` did `sql.replace("?", "%s")`, corrupting literal `?` and unescaped `%` | `rebind_param_markers()` rebinds outside literals/identifiers |
| Backend swap closed a pool other threads were using; a dead live backend was never re-probed; SL health check forced an ERP login per request | Locked selection, in-flight-aware retirement, re-probe of live backends, query-level failover, cached pings |
| Unbounded `await file.read()` before the size check; uploads never deleted | Read capped, oversize rejected before buffering, 1 h sweeper deletes stale uploads, non-text uploads rejected |
| Only the last table of an answer survived into history | Every dataset is persisted (`tables[]`) and replayed |
| Frontend fabricated answers on any API error (invented counts, table, chart, unlabelled), auto-"signed in" with `demo-token`, faked sessions/transcript on failure | All fabricated fallbacks removed; outages and refusals are reported as such |
| `sap_token` threaded through the agent but unused; `MOCK_TENANTS` half-wired | Dead parameter removed, tenant registry env-driven with per-tenant overrides and strict lookup |
| Money shown as `1,234,567.89` while the prompt promised ₹12,34,567 | `format_money()` (backend summaries) and `lib/format.ts` (tables, axes, tooltips) do it in code, not by asking nicely |
| Lint script (`eslint .`) exited 127 — eslint wasn't even a dependency; no CI at all | Flat `eslint.config.mjs` + deps, `ops/github-actions-ci.yml` (pytest, ruff, tsc, eslint, build, credential-default grep) |
| `migrate_db.py --check` always exited 0, even when simulated | Validates config, prints why each source was rejected, non-zero exit when it isn't live (`--require-live`) |


### Show-stoppers (the app could not work as described)

| # | Problem | Fix |
|---|---|---|
| 1 | `requirements.txt` was missing **SQLAlchemy**, **aiosqlite** and **python-multipart** — a clean `pip install -r requirements.txt` produced a backend that crashed on import. | Full, pinned-minimum requirements list. |
| 2 | Model name was hard-coded in the source. | Now `CIRA_MODEL` env (default `openrouter/free`, OpenRouter's auto-routed free tier), plus a deterministic planner fallback when no key is set. |
| 3 | Real HANA rows are `decimal.Decimal` / `datetime.date` / `bytes`; `json.dumps` raises on all three, so the **first live query would have killed the SSE stream**. Only the 2-row mock data ever serialised. | `sap/serialize.py` coerces every value; regression tests cover Decimal/date/bytes/NaN. |
| 4 | Unknown entity names silently fell back to `TABLE_MAP.get(entity, "ORDR")` → asking for “deliveries” returned **sales orders presented as deliveries**. | Unknown tables raise an explanatory error with close matches; the agent then looks the name up. |
| 5 | `DocStatus = 'Open'` was sent to HANA, but B1 stores `'O'` → “open invoices” always returned 0 rows. Service Layer needed `bost_Open`. | Value encoding/decoding layer for both paths. |
| 6 | The whole 500-row result was pushed into the LLM prompt (slow, expensive, context overflow). | Tools return counts/totals/8 sample rows; the full dataset goes to the browser over a side channel (ResultBus). |
| 7 | Session tokens were **unsigned base64 minted in the browser** — anyone could impersonate `ADMIN-001` from the console. | Server-side `POST /auth/login`, HMAC-SHA256 signed tokens, expiry + constant-time verification; unsigned/tampered/expired tokens rejected (tested). |
| 8 | React hooks were declared **after** early `return`s in `DataCard` and `ChartCard` → “rendered fewer hooks than expected” crash whenever an empty/chart-less answer followed a normal one. | All hooks hoisted above every return. |
| 9 | Frontend hard-coded `http://localhost:8000`, so it only worked when the browser ran on the API host. | All calls go to `/api/*`, proxied by Next (`next.config.mjs` → `BACKEND_ORIGIN`). |
| 10 | `xlsx` was installed from `https://cdn.sheetjs.com/...tgz`; `npm install` fails wherever that CDN is blocked (corporate proxy, the RDP box, CI). | Switched to `write-excel-file` from the npm registry, with an automatic CSV fallback. |
| 11 | Charts were fed all 500 raw rows and guessed axes from entity names → 500 bars, or a string on the Y axis. | Server-side aggregation: dimension/measure detection, group + sort + top-N + “Others”, month bucketing for trends, ≤21 points. |
| 12 | Every SAP query opened a brand-new TLS+HANA session (1–3 s each on a remote Azure host) and never reused it. | Connection pool with liveness checks; Service Layer sessions now expire/renew and retry on 401, and follow `@odata.nextLink` paging. |

### Also fixed

- `query_company_docs` returned one hard-coded travel policy for every question → now a real
  BM25 search over `Backend/knowledge/*.md` (4 policies shipped, drop in more).
- `year` parameter was documented but never applied to the WHERE clause → implemented (and
  `date_from`/`date_to`, “last quarter”, “this year”, …).
- No aggregation support at all (“which vendors have the highest PO value?” fetched raw rows
  and hoped) → `GROUP BY` + aggregates end-to-end, including a Service-Layer fallback that
  aggregates in Python and *says so*.
- Mock data was returned silently as if live → every response carries `simulated`, the UI shows a
  `SIMULATED` badge and a header pill, and the summary says it out loud.
- CORS was pinned to `http://localhost:3000` → configurable (`CIRA_ALLOWED_ORIGINS`).
- `/generate_title` and `/chat` had no client-disconnect or error handling → SSE now emits
  `status`, `backend`, `error` and `done` events, persistence happens in a `finally` block.
- DataCard showed only the first 5 columns and every row at once → pagination (25/50/100/500),
  column picker, sticky sortable headers, numeric alignment, Excel/CSV/JSON/copy, “Show SQL”.
- ChartCard had no Area chart despite emitting `chartType: 'area'` (it rendered a pie instead) → 4
  chart types, theme-aware colours, compact axis formatting.
- Light mode was unreadable (white text on white); profile values were saved but never reloaded;
  the greeting was hard-coded “Good morning, Alex.” → all fixed.
- `crypto.randomUUID()` crashes on plain-HTTP origins (exactly how an RDP deployment is reached)
  → fallback added.
- `X-Title` header contained an em dash → non-ASCII HTTP header, which raises before the request
  is even sent to OpenRouter.
- `cira.db` was committed to git despite `.gitignore`; runtime data now lives in `Backend/data/`.

---

## 4. Configuration

Everything lives in `Backend/.env` (see `Backend/.env.example`). Highlights:

Nothing below has a credential or hostname default — `–` means "must be set, or
this source is not used".

| Variable | Default | Notes |
|---|---|---|
| `CIRA_DATA_SOURCE` | `auto` | `auto` = every enabled source in order. `hana` pins HANA and fails loudly if unreachable. |
| `CIRA_DATA_SOURCE_ORDER` | `hana,service,mssql,simulator` | Preference order for `auto`. **HANA is first.** |
| `HANA_HOST` / `HANA_PORT` | – / `30013` | 30013 is the instance-00 system port. If the company schema is not visible, try the tenant SQL port `3<instance>15` (e.g. 30015). |
| `HANA_USER` / `HANA_PASSWORD` | – | **Read-only** technical user with SELECT on the company schema only — not `SYSTEM`. |
| `HANA_SCHEMA` | – | Company DB. If it does not exist, CIRA auto-detects schemas containing `OADM` and logs a warning. |
| `HANA_EXTRA_SCHEMAS` | – | Extra schemas the raw-SQL tool may read (SQL guard allowlist). |
| `MSSQL_*` | – | Only if B1 runs on SQL Server; `MSSQL_SCHEMA` defaults to `dbo`. |
| `SAP_B1_*` | – | Service Layer (OData, port 50000). Also the only path that can write. |
| `CIRA_TENANTS`, `CIRA_TENANT_<NAME>_<SETTING>` | – | Register the company DBs users may sign in to; per-tenant overrides. |
| `OPENROUTER_API_KEY`, `CIRA_MODEL` | – | Any OpenAI-compatible endpoint via `OPENROUTER_BASE_URL`. `GROQ_API_KEY` enables the mic button. |
| `CIRA_SECRET_KEY` | auto-generated once | Set explicitly in production (multi-host, survives redeploys). |
| `CIRA_ADMIN_ID` / `CIRA_ADMIN_PASSWORD` | – | Bootstrap admin. Empty ⇒ there is no admin account. |
| `CIRA_ALLOW_ANY_EMPLOYEE` | `false` | Demo mode. Do not enable near production data. |
| `CIRA_SAP_WRITE_ENABLED` | `false` | Gates `POST /sap/write` (see §9). |
| `CIRA_SAP_WRITE_ROLES` / `CIRA_SAP_WRITE_ENTITIES` | `admin` / 7 B1 entity sets | Role + entity allowlist for writes. |
| `CIRA_DEFAULT_ROW_LIMIT` / `CIRA_MAX_ROW_LIMIT` | 500 / 10000 | |
| `CIRA_MAX_STREAMED_ROWS` / `CIRA_MAX_PERSISTED_ROWS` | 2000 / 2000 | Browser payload / history rows. |
| `CIRA_ALLOWED_ORIGINS` / `CIRA_ALLOWED_ORIGIN_REGEX` | – | Required while `CIRA_STRICT=true` (default). No wildcard-with-credentials mode any more. |
| `CIRA_ALLOW_SIMULATOR` | `true` | Set `false` in production: then a dead HANA is an error, never sandbox data. |
| `CIRA_AUDIT_ENABLED` / `CIRA_AUDIT_LOG` | `true` / `Backend/data/audit.jsonl` | Who queried what, and every write attempt. |

Frontend: `BACKEND_ORIGIN` (server-side proxy target) and optionally `NEXT_PUBLIC_API_URL`.

---

## 5. Deploying to the RDP machine (where HANA is reachable)

```bat
git pull origin main

cd Backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then fill in HANA_*, SAP_B1_*, CIRA_ALLOWED_ORIGINS, CIRA_ADMIN_*, OPENROUTER_API_KEY
python ..\scripts\diagnose.py --require-live   # exit 1 until a REAL ERP answers
python migrate_db.py --check --require-live    # migration + config validation
uvicorn main:app --host 0.0.0.0 --port 8000

cd ..\Frontend
npm ci
npm run build
npm start                       # or serve behind IIS/nginx
```

`diagnose.py` prints the effective configuration, tests the TCP port for each
source, logs into HANA / SQL Server / the Service Layer and reports which
backend would answer. `migrate_db.py --check --require-live` additionally
migrates the history DB and **exits non-zero while the answer is simulated**, so
a deploy script can fail instead of quietly demoing. If it says *simulated*,
CIRA is not on live data.

### Verifying live HANA quickly

```bash
python ../scripts/diagnose.py                 # config + TCP + real login for every source
python -c "import os,socket;from dotenv import load_dotenv;load_dotenv('.env');h=os.environ['HANA_HOST'];p=int(os.environ.get('HANA_PORT',30013));socket.create_connection((h,p),5);print(h,p,'open')"
curl -s localhost:8000/health
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/sap/health | jq   # needs a token now
```

Tunneling from outside the company network: `start_ssh_tunnel.bat` reads
`tunnel.env` (git-ignored) and prompts for the SSH password — it no longer
stores one. The same file used to contain the RDP machine's password in
plaintext; that password must be rotated.

Common causes when it stays on the sandbox:
- wrong port (30013 is SYSTEMDB on instance 00; tenant DBs listen on 3xx15),
- Azure NSG / Windows Firewall not opened for the SQL port,
- `HANA_ENCRYPT=true` against a server without TLS → set `HANA_ENCRYPT=false`,
- user lacks `SELECT` on the company schema or on `SYS` catalog views.

Reverse proxy note: SSE must not be buffered. The backend sends `X-Accel-Buffering: no`; in nginx
also set `proxy_buffering off;` for `/chat`.

---

## 6. API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/auth/login` | `{employee_id, password}` → signed token |
| `GET` | `/auth/me` | current user |
| `GET` | `/health` | liveness (public) |
| `GET` | `/sap/health` | active backend, schema, table count, probe log |
| `GET` | `/sap/tables?pattern=` | catalog listing |
| `GET` | `/sap/table/{name}` | columns + sample rows |
| `POST` | `/chat` | SSE stream: `backend`, `status`, `source`, `chunk`, `tabular`, `chart`, `form`, `error`, `done` (all except login/health need a token) |
| `POST` | `/sap/write` | Create one record via the Service Layer. Disabled unless `CIRA_SAP_WRITE_ENABLED=true`, admin-role only, entity allowlist, audited |
| `POST` | `/transcribe` | Groq Whisper proxy; 503 unless `GROQ_API_KEY` is set, audio-type + size validated |
| `GET` | `/sessions`, `/history/{id}` | conversation list / transcript (ownership enforced) |
| `PUT`/`DELETE` | `/session/{id}` | rename / delete |
| `POST` | `/generate_title` | short chat title |
| `POST` | `/upload` | attachment (text/CSV extracted and sent as context) |

---

## 7. Tests

```bash
# optional: enable CI once (the workflow ships under ops/ so it can be reviewed first)
mkdir -p .github/workflows && cp ops/github-actions-ci.yml .github/workflows/ci.yml

cd Backend
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # 129 tests, no ERP / API key / network required
.venv/bin/python -m ruff check .       # clean; the CI gate runs it too
```

CI lives at **`ops/github-actions-ci.yml`** — copy it into place with
`mkdir -p .github/workflows && cp ops/github-actions-ci.yml .github/workflows/ci.yml`
(it is stored outside `.github/` because the automation that produced this pass
cannot push workflow files). It runs pytest, `ruff`, `tsc --noEmit`, `npm run lint`,
`next build` and a grep check that no credential default ever reappears in `config.py`.

Coverage includes the read-only **and scoped** SQL guard (injection, DDL, `SYS.USERS`,
locking clauses), dialect-correct row caps and param rebinding (T-SQL `OFFSET/FETCH`,
`%`-escaping), the query builder, B1 code translation, live queries against the sandbox
(filters, year windows, group-by, joins, row caps), chart aggregation, token forgery/expiry,
cross-employee IDOR on sessions and history, SSE streaming shape, the **full LangGraph
tool-calling loop against a mock OpenAI-compatible server**, the write-path gating matrix
(disabled / wrong role / off-allowlist entity / sandbox refusal), audit-trail contents
(including "a password never reaches the log"), and the config policy tests that keep
credentials out of `config.py` and HANA at the front of the order.

---

## 8. Layout

```
Backend/
  main.py             FastAPI app: auth, chat SSE, sessions, diagnostics, uploads, /sap/write gating
  agent.py            LangGraph ReAct agent, tools, SSE events, deterministic fallback planner
  auth.py             HMAC-signed session tokens, role gate, tenant binding
  audit.py            append-only JSONL audit trail (logins, SQL, writes, uploads)
  config.py           single source of truth: enablement, tenants, policy flags, validate()
  database.py         SQLAlchemy models + WAL SQLite (data/cira.db)
  docs_store.py       BM25 policy search (RAG over Backend/knowledge/*.md)
  migrate_db.py       idempotent migration + config/SAP check (non-zero exit if not live)
  sap/
    router.py         backend selection (HANA first), locking, failover, retirement, query API
    base.py           DataBackend contract: dialect, capabilities, sql_schema, allowed_schemas
    hana_backend.py   hdbcli pool (bounded), SYS catalog introspection, schema auto-detect
    mssql_backend.py  SQL Server driver (B1 on MS SQL), bracket identifiers, query timeout
    service_layer.py  OData client (sessions, paging, enum mapping, identifier validation)
    sim_backend.py    offline SAP B1 sandbox (34 tables, ~25k rows); writes refuse, never fake
    query_spec.py     structured, injection-safe SELECT builder (dialect-aware)
    sql_guard.py      read-only + schema scoping + row caps + paramstyle + HANA→SQLite bridge
    serialize.py      HANA type → JSON coercion (Decimal/date/bytes/NaN) + INR formatting
    entities.py       B1 aliases, preferred columns, code maps
    charts.py         dimension/measure detection + aggregation
  tests/              pytest suite (129 tests)
Frontend/
  app/page.tsx        chat UI, SSE, session list; no fabricated fallback data
  app/components/DataCard.tsx   pagination, column picker, exports, ₹ / en-IN formatting
  app/ChartCard.tsx   bar / line / area / pie
  app/components/DynamicFormCard.tsx  data-entry form → /sap/write (states simulated vs real)
  lib/export.ts       xlsx / csv / json export
  next.config.mjs     /api/* → backend proxy
scripts/
  diagnose.py         config + TCP + login probe for every source (--require-live)
  show_sap_entities.py  print the alias registry (dev aid)
```

Untracked on purpose (still on disk in this checkout, but out of the repo):
`cloudflared.exe` (54 MB binary — download it on the target machine), `Frontend_legacy/`
(superseded copy of the UI) and the `WhatsApp Image …jpeg` design drop-ins. `Backend/.env`,
`tunnel.env`, `*.db` and `Backend/data/` are ignored as before.

## 9. Security model, and what is still open

**In place now**
* Server-minted HMAC-SHA256 session tokens; signature, `exp` and `iat` enforced; no
  client-minted or unsigned tokens; every endpoint except `/health` and `/auth/login` needs one.
* Ownership checks on `/sessions`, `/history`, rename and delete (IDOR-tested).
* No credentials, hostnames or admin accounts in source; `.env.example` is placeholders.
* SQL is read-only *and* schema-scoped; identifiers catalog-validated; values bound.
* CORS cannot be `*` with credentials; strict mode makes it a startup error.
* SAP writes: disabled by default, admin-role only, entity allowlist, bounded payload, and
  never served by the sandbox (it refuses instead of faking a success).
* Audit trail of logins, ERP queries and write attempts.

**Open items — read before going live**
1. **Auth is still a bootstrap admin + optional demo mode.** Wire `auth.authenticate()` to
   your IdP (or an `OUSR` lookup) before exposing this to employees.
2. **No per-user authorisation at the ERP.** Every session shares one read-only technical
   user, so *any* signed-in employee can see *any* table the grantor allowed (salaries,
   `OUSR`). Row/column-level security needs per-user SAP identities or a view layer per
   role — `exchange_for_sap_token()` in `auth.py` is the documented seam and is still a stub.
3. **Rotate three credentials today.** Committed in `8987ed4` (so they are in history even
   though the files are now clean):
   * the **RDP machine's login password**, in plain text, in `start_ssh_tunnel.bat` — plus its
     public IP and username;
   * the **SQL Server `sa` password** for the live company DB, as a default in `config.py`;
   * the **HANA/Service Layer public IP** used as a default in `config.py` / `.env.example`.

   Deleting them from the working tree does *not* un-leak them. Rotate on the server first,
   then rewrite history if the repo is shared or public:

   ```bash
   pip install git-filter-repo
   git filter-repo --invert-paths --path start_ssh_tunnel.bat --force
   git push --force --mirror        # coordinate with everyone who has cloned it
   ```

   Also assume the SSH host key/fingerprint was exposed to anyone with repo access and
   restrict RDP source IPs while you rotate.
4. **Prompt-injection is unmitigated beyond read-only SQL.** A document or ERP comment text
   telling the model to run another query is still possible; the guard limits *damage*, not
   *reach*. Keep the technical user read-only and the write path closed.
5. **The audit log contains table/filter metadata** and rotates at 50 MB; ship it to your
   SIEM and keep it off the ERP box if disk is tight.
