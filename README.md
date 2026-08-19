# CIRA — Corporate Intelligence & Reporting Assistant

Ask your SAP Business One (HANA) company database anything in plain English and get an
interactive table, a chart and a two-line executive summary back.

```
Frontend (Next.js 16 / React 19)  ──/api/*──►  Backend (FastAPI)  ──►  SAP HANA  (SQL, full depth)
                                                                  ├─►  SAP B1 Service Layer (OData)
                                                                  └─►  Offline SAP B1 sandbox (dev/CI)
```

---

## 1. Quick start

### Backend

```bash
cd Backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # fill in HANA_* / SAP_B1_* / OPENROUTER_API_KEY
python migrate_db.py --check                            # migrate cira.db + probe SAP connectivity
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd Frontend
npm install
npm run dev            # http://localhost:3000  (proxies /api/* to the backend)
# production: npm run build && npm start
```

Sign in with `admin` / `asdfghjkl;` (configurable, see `CIRA_ADMIN_*`), or any employee ID +
password while `CIRA_ALLOW_ANY_EMPLOYEE=true`.

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

Safety rails: single statement, `SELECT`/`WITH` only, DDL/DML/`CALL` rejected even in sub-queries,
identifiers validated against the live catalog, values always bound as parameters, and a row
cap is injected when the author forgot one.

Business semantics are built in: friendly names (`invoices → OINV`, `vendors → OCRD`,
`journal lines → JDT1`, ~80 aliases), status words translated to B1 codes
(`Open → 'O'`, `vendor → 'S'`) on the way in and back to words on the way out,
per-table “preferred columns” so a 150-column header table doesn’t drown the UI,
and known date/amount/party columns per table for automatic charting.

---

## 3. What was broken, and what changed

### Show-stoppers (the app could not work as described)

| # | Problem | Fix |
|---|---|---|
| 1 | `requirements.txt` was missing **SQLAlchemy**, **aiosqlite** and **python-multipart** — a clean `pip install -r requirements.txt` produced a backend that crashed on import. | Full, pinned-minimum requirements list. |
| 2 | Model name was `openrouter/free`, which does not exist → every LLM call failed. | `CIRA_MODEL` env (default `anthropic/claude-3.5-sonnet`), plus a deterministic planner fallback when no key is set. |
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

| Variable | Default | Notes |
|---|---|---|
| `CIRA_DATA_SOURCE` | `auto` | `auto` → HANA → Service Layer → sandbox. Force with `hana`, `service`, `simulator`. |
| `HANA_HOST` / `HANA_PORT` | `20.204.5.237` / `30013` | 30013 is the instance-00 system port. If the company schema is not visible, try the tenant SQL port `3<instance>15` (e.g. 30015). |
| `HANA_USER` / `HANA_PASSWORD` | – | Use a **read-only** technical user. |
| `HANA_SCHEMA` | `CIRA_DEMO_NEW` | Company DB. If it doesn’t exist, CIRA auto-detects schemas containing `OADM` and logs a warning. |
| `SAP_B1_*` | – | Service Layer fallback (port 50000). |
| `OPENROUTER_API_KEY`, `CIRA_MODEL` | – | Any OpenAI-compatible endpoint works via `OPENROUTER_BASE_URL`. |
| `CIRA_SECRET_KEY` | auto-generated | Set explicitly in production (multi-host, survives redeploys). |
| `CIRA_DEFAULT_ROW_LIMIT` / `CIRA_MAX_ROW_LIMIT` | 500 / 10000 | |
| `CIRA_ALLOWED_ORIGINS` | any (dev) | Comma-separated list in production. |

Frontend: `BACKEND_ORIGIN` (server-side proxy target) and optionally `NEXT_PUBLIC_API_URL`.

---

## 5. Deploying to the RDP machine (where HANA is reachable)

```bash
git pull origin main

cd Backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then fill in HANA_PASSWORD, SAP_B1_PASSWORD, OPENROUTER_API_KEY
python migrate_db.py --check    # ← confirms which backend CIRA actually picked
uvicorn main:app --host 0.0.0.0 --port 8000

cd ..\Frontend
npm install
npm run build
npm start                       # or serve behind IIS/nginx
```

`migrate_db.py --check` prints the active backend, schema and visible table count, plus the exact
reason each candidate failed. If it says *simulated*, CIRA is **not** on live data yet.

### Verifying live HANA quickly

```bash
python -c "import socket;socket.create_connection(('20.204.5.237',30015),5);print('port open')"
curl -s localhost:8000/health
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/sap/health | jq
```

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
| `POST` | `/chat` | SSE stream: `backend`, `status`, `source`, `chunk`, `tabular`, `chart`, `error`, `done` |
| `GET` | `/sessions`, `/history/{id}` | conversation list / transcript (ownership enforced) |
| `PUT`/`DELETE` | `/session/{id}` | rename / delete |
| `POST` | `/generate_title` | short chat title |
| `POST` | `/upload` | attachment (text/CSV extracted and sent as context) |

---

## 7. Tests

```bash
cd Backend
.venv/bin/python -m pytest -q          # 52 tests, no ERP / API key / network required
```

Coverage includes the read-only SQL guard (injection & DDL attempts), HANA type serialisation,
the query builder, B1 code translation, live queries against the sandbox (filters, year windows,
group-by, joins, row caps), chart aggregation, token forgery/expiry, cross-employee IDOR on
sessions and history, SSE streaming shape, and the **full LangGraph tool-calling loop against a
mock OpenAI-compatible server** (so the LLM path is verified without a paid key).

---

## 8. Layout

```
Backend/
  main.py             FastAPI app: auth, chat SSE, sessions, diagnostics, uploads
  agent.py            LangGraph ReAct agent, tools, SSE events, deterministic fallback planner
  auth.py             HMAC-signed session tokens
  config.py           single source of truth for every setting
  database.py         SQLAlchemy models + WAL SQLite
  docs_store.py       BM25 policy search (RAG over Backend/knowledge/*.md)
  migrate_db.py       idempotent migration + SAP connectivity check
  sap/
    router.py         backend selection, failover, query execution API
    hana_backend.py   hdbcli pool + SYS catalog introspection
    service_layer.py  OData client (sessions, paging, enum mapping)
    sim_backend.py    offline SAP B1 sandbox (34 tables, ~25k rows)
    query_spec.py     structured, injection-safe SELECT builder
    sql_guard.py      read-only validation + row caps + HANA→SQLite bridge
    entities.py       B1 aliases, preferred columns, code maps
    charts.py         dimension/measure detection + aggregation
  tests/              pytest suite
Frontend/
  app/page.tsx        chat UI, DataCard (pagination, column picker, exports)
  app/ChartCard.tsx   bar / line / area / pie
  lib/export.ts       xlsx / csv / json export
  next.config.mjs     /api/* → backend proxy
```
