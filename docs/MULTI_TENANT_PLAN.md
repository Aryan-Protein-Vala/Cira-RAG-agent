# Multi-tenant plan — external clients, their own SAP company DBs

Target picture:

```
                             company server (RDP box)
  external client browser ──HTTPS──►  reverse proxy 443
                                          │
                                          ▼
                                   Next.js (3000)
                                          │  /api/*
                                          ▼
                                   FastAPI (127.0.0.1:8000)
                                          │  per-tenant connection
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                    HANA schema     HANA schema     HANA schema
                    CLIENT_A        CLIENT_B        CLIENT_C
```

Both SAP B1 hosting shapes work with the same design:

* **Shape 1 — one HANA instance, one company schema per client** (the usual SAP-partner hosting
  model). A tenant differs only by `schema` + credentials.
* **Shape 2 — each client has their own HANA host/VM.** A tenant differs by `host/port/schema/
  credentials`. Identical code, more fields in the registry.

---

## 1. What has to change in the code

Today the SAP backend is a **process-wide singleton** built from `.env`
(`sap/router.py::_selector`). Multi-tenancy means making it **keyed by tenant**. That is the whole
refactor — roughly 1–2 days, contained to four places:

| Where | Change |
|---|---|
| `sap/router.py` | `_Selector` → `dict[tenant_id, _Selector]`, with an LRU/idle eviction so 50 tenants don't hold 200 HANA connections. Every public function takes `tenant` as its first argument. |
| `agent.py` | Tools close over the caller's `tenant`, exactly like they close over `employee_id` today. |
| `auth.py` / `main.py` | The signed token carries `tenant_id`; every request resolves its tenant from the token, never from a header or query string the client controls. |
| `database.py` | `tenant_id` column on `chat_sessions` / `chat_messages`, added to every WHERE clause next to `employee_id`. |

New: a `tenants` table (or `tenants.json` for the first few):

```
tenant_id, display_name, hana_host, hana_port, hana_schema,
hana_user, hana_password_encrypted, service_layer_url, company_db,
sl_user, sl_password_encrypted, row_limit, llm_model, active
```

Plus a `tenant_users` mapping (employee id / e-mail domain → tenant), so login resolves the tenant
server-side.

---

## 2. Isolation — the part that must be perfect

One tenant reading another tenant's ERP is the failure that ends the product. Four enforcement
points, all server-side:

1. **Token binds the tenant.** `tenant_id` is inside the HMAC-signed payload. A client cannot
   change it.
2. **Catalog scoping.** `_resolve_table()` already validates every table against the live catalog —
   it must be the *tenant's* catalog. Unknown table → error, never a fallback.
3. **Raw SQL guard.** Add a rule to `sql_guard`: reject any statement containing a schema qualifier
   that isn't the tenant's own schema (`"OTHER_CO"."OINV"`), and reject `SYS.` access except the
   catalog views we introspect with, filtered by `SCHEMA_NAME = <tenant schema>`.
4. **Per-tenant DB user.** Each tenant connects with a HANA user that only has `SELECT` on its own
   schema. Then even a bug in layers 1–3 hits a permission error instead of leaking data.

Add tests that assert tenant A cannot read tenant B by table name, by qualified SQL, or by
replaying tenant B's session id — mirroring the IDOR tests that already exist.

---

## 3. Security checklist before any external user gets a URL

- [ ] `CIRA_ALLOW_ANY_EMPLOYEE=false` — **today any ID + any password signs in.** Replace
      `auth.authenticate()` with real credentials: Azure AD / Entra ID SSO (best), or per-user
      password hashes (argon2/bcrypt) in the tenant registry.
- [ ] `CIRA_SECRET_KEY` set explicitly; rotate procedure documented.
- [ ] HTTPS only, HSTS, `CIRA_ALLOWED_ORIGINS` pinned to the real hostname.
- [ ] Rate limiting per user and per tenant (chat is expensive: SQL + LLM tokens).
- [ ] Audit log: who asked what, which SQL ran, how many rows left the building.
- [ ] Row-cap and export-size policy per tenant.
- [ ] **LLM data flow disclosure.** Question text, column names and up to 8 sample rows go to
      OpenRouter. For external clients that needs a DPA, an opt-out, or a self-hosted model
      (vLLM/Ollama behind `OPENROUTER_BASE_URL` — the code already supports any
      OpenAI-compatible endpoint). Decide this *before* onboarding a client, not after.
- [ ] Backup of `cira.db` (chat history) and the tenant registry.

---

## 4. Networking reality check

CIRA must be able to open a TCP connection to each tenant's HANA. Options, best first:

1. **All company DBs on the same server as CIRA** → localhost, nothing to do. Start here.
2. Client HANA elsewhere but on a private link → site-to-site VPN / Azure private peering.
3. Client HANA behind their own firewall → they open the SQL port to your static egress IP, or you
   run a small outbound-only connector on their side. Never ask a client to expose 30015 publicly.
4. Only their Service Layer is reachable → CIRA already supports Service Layer as a data source; it
   loses joins and exact GROUP BY totals, so flag those answers as approximate (the code already
   emits that warning).

---

## 5. Recommended order

**Phase 0 — now (this week).** Get single-tenant live on the RDP box (`DEPLOYMENT.md`). Prove real
HANA answers with hundreds of rows, real charts, acceptable latency. Everything else is guesswork
until this is done.

**Phase 1 — before any external user (2–4 days).** Real authentication, HTTPS + reverse proxy,
rate limiting, audit log, LLM data-flow decision. This is non-negotiable and independent of
multi-tenancy — one internal user over the internet needs it just as much as ten clients.

**Phase 2 — multi-tenancy (1–2 weeks).** Tenant registry, per-tenant routing, isolation tests,
per-tenant HANA users, an admin page to onboard a client (add tenant → test connection → assign
users). Ship with 2 tenants (one being your own company) before selling it to 10.

**Phase 3 — commercial hardening.** Per-tenant usage metering and LLM cost caps, plan limits,
tenant-level branding, status page, backup/restore drill.

**Phase 4 — agentic writes** (see the design discussed separately), per-tenant approval limits,
separate write-enabled B1 user per tenant.

Do **not** start Phase 2 before Phase 0 is green: multi-tenant routing built on top of an
unvalidated connection just multiplies the debugging surface.
