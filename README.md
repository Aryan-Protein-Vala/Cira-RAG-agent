# B1 Copilot — SAP Business One SaaS Platform

![B1 Copilot Logo](assets/logo.jpg)

Ask your SAP Business One (HANA) company database anything in plain English and get an
interactive table, a chart and a two-line executive summary back. 

B1 Copilot is now a fully white-labeled multi-tenant B2B SaaS platform equipped with Super Admin, Partner Admin, Data Migration tools, and strict Role-Based Access Controls (RBAC).

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
python migrate_db.py --check                            # migrate database + probe SAP connectivity
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd Frontend
npm install
npm run dev            # http://localhost:3000  (proxies /api/* to the backend)
# production: npm run build && npm start
```

**Nothing is mandatory to get a running system**: with no HANA reachable and no LLM key,
B1 Copilot boots into the offline SAP B1 sandbox with a deterministic planner and still renders
real tables and charts — clearly labelled `SIMULATED` so nobody mistakes it for production data.

---

## 2. Multi-Tenant SaaS Architecture (New!)

B1 Copilot has been completely upgraded into a Tiered SaaS Application. 

| Portal | Access | Responsibilities |
|---|---|---|
| **Super Admin** | `/superadmin` | Global console to provision Reseller Partners. Can assign plans (Pilot, Read Only, Read / Write Full, Migration), set tenant quotas, and manage white-labeling brand names. |
| **Partner Admin** | `/admin` | Dashboard for Reseller Partners to connect and manage their clients' SAP B1 databases. Partners can toggle `write_enabled` on a per-tenant basis. |
| **End User / Client** | `/` | The main B1 Copilot chat interface for interacting with the SAP database. |

### Data Migration Tool
Partner Admins have access to the **Data Migration Tool** (`/admin/migration`) to onboard legacy client data into SAP B1 effortlessly. 
- Features an Excel/CSV uploader.
- Uses `difflib` for robust **fuzzy matching**, seamlessly mapping irregular client headers (e.g., "Vendor Name") to strict SAP defaults (e.g., `CardName`).
- Validates data against the SAP Service Layer API and pushes records securely in batches.

---

## 3. How deep the SAP access goes

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

## 5. Tests & Accuracy Harness

```bash
cd Backend
.venv/bin/python -m pytest -q          # 52 unit tests, no ERP / API key / network required
.venv/bin/python tests/accuracy/runner.py # 60-question end-to-end LLM Accuracy Harness
```

The system features an automated Accuracy Harness that queries the LLM and generating/executing SQL 60 separate times over sandbox data to ensure the generation logic is perfectly accurate.

---

## 6. Layout

```
Backend/
  main.py             FastAPI app: auth, chat SSE, sessions, diagnostics, uploads
  agent.py            LangGraph ReAct agent, tools, SSE events, deterministic fallback planner
  auth.py             HMAC-signed session tokens
  config.py           single source of truth for every setting
  database.py         SQLAlchemy models + WAL SQLite (Tenants, Partners, SuperAdmin)
  admin_routes.py     SaaS Routing logic for Multi-tenancy
  migration_routes.py Data Migration tool for pushing Excel/CSV into SAP Service Layer
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
  tests/              pytest suite and 60-question LLM Accuracy Harness
Frontend/
  app/page.tsx             chat UI, DataCard (pagination, column picker, exports)
  app/admin/page.tsx       Partner Admin UI
  app/superadmin/page.tsx  Super Admin UI
  app/ChartCard.tsx        bar / line / area / pie
  lib/export.ts            xlsx / csv / json export
  next.config.mjs          /api/* → backend proxy
```
