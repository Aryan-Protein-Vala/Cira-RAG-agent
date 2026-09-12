# CIRA / B1 Copilot — 60-day income plan, 6–12 month defence

Read this first. Everything below is built from the actual repository (`main` @ `b1bc619`), the
two RDP branches (`new-final-rdp-version` @ `9fe98f6`, `final-version-of-rdp` @ `5cf3942`) and
public sources cited inline. Numbers I could not verify are marked `UNVERIFIED`.

---

## Disagreements, stated up front

1. **The accuracy harness was measuring the wrong thing.** Until this week it scored PASS when
   the agent called `sap_query` with a table name that appeared in a list — it never compared the
   answer, the SQL, the row count or the value. `results.json` recorded "8/20" from that logic.
   Any number produced by it is worthless as an accuracy claim. It has been rewritten to grade
   eight independent checks and to compute expected values itself from the sandbox DB, but the
   suite currently has **zero questions with expected values filled in** — so the honest status
   today is `accuracy: unmeasured`. Do not put a percentage in a deck until `ci_gate.py` reports
   value-verified counts.
2. **I cannot give you 20 verified named decision-makers with emails/LinkedIn URLs for each A
   country.** Every "top N SAP partners in <country>" page is an SEO self-ranking (the #1 entry is
   the site that published it). Names and roles are sometimes on partner "About/Leadership"
   pages; personal emails and LinkedIn profiles are not reliably public, and inventing them is the
   one thing that would destroy the wedge. §4 gives you verified company names + the decision-maker
   *role*, plus the exact 20-minute method to convert that into named people. Treat this as a
   correction to the brief, not an omission.
3. **The migration tool, not the chatbot, is the wedge — but it is not built yet.** What exists is
   `upload → validate → push` for Business Partners and Items only. Opening stock and A/R open
   items (the two objects every B1 go-live actually gets wrong) return HTTP 501 on purpose.
   §3 prices the remaining 60–80 hours.
4. **₹5,000/company/month in foreign markets is not a business at 15 clients.** Two clients at
   ₹5k is ₹10k/month. The read tier is a *land* price, not a revenue line: it captures the
   relationship and makes the migration and write tiers sellable. §5 shows the arithmetic.
5. **"SAP ships this free" is arithmetically wrong and the FP 2608 answer is now stronger than
   the old one**: Ask AI and AI-assisted UDQ need FP 2608 **plus** the Web Client **plus** a BTP
   enterprise account with AI Core/Generative AI Hub consumption
   ([softcoresolutions](https://softcoresolutions.com/blog/ai-in-sap-business-one/)); FP 2608 also
   ships an official **MCP Server sample** that exposes Service Layer entities as agent tools
   ([SAP Help](https://help.sap.com/docs/SAP_BUSINESS_ONE/bb89a9939c294f14a7f532f7e76ade9e)) — that is
   validation of this category, and it is also the deadline. You have roughly 12–18 months before
   "talk to your B1 data" is a checkbox in the product.
6. **Never direct-INSERT into B1 tables, and never present an unmeasured accuracy figure.**
   Both were live defects in this repo (the sandbox write path silently returned a random DocEntry
   without writing; the harness graded table names). Both are fixed in code this week. They stay
   as constraints, not preferences.

---

# 1. Code truth

## 1.1 What the code actually does, area by area

Hours are *my* estimate to reach "sellable to a stranger", assuming one developer (you) and no
live customer access.

| Area | Works today | Demo-only / unproven | Missing | Hours to finish |
|---|---|---|---|---|
| Query generation | `agent.py` planner → `sap/query_spec.py` builds parameterised SQL: identifiers regex-validated and quoted, values bound, dialects handled (`LIMIT` vs `TOP`; SQL Server row-cap bug fixed this week in `sql_guard.apply_row_limit`). Deterministic planner runs with no LLM key. | The LLM path has never been run with a real key in this environment; no recorded transcript proves a natural-language question becomes the right SQL. | Schema-linking cache (config has `SCHEMA_CACHE_TTL_S` = 900 but no warm cache), query-result provenance ("this number came from OINV.DocTotal, 2 rows"), self-check when an aggregate returns 0 rows. | 24 |
| Schema introspection | HANA: `SYS.TABLES` / `SYS.COLUMNS` + column comments, company schema discovered from `OADM`. SQL Server: `sys.tables` / `sys.columns`. Simulator: 42 curated tables. Table aliases + human descriptions in `sap/entities.py`. | HANA and MSSQL paths are unexercised against a real server (no credentials in this workspace). | Verified column-list freeze for the ~40 tables that matter, so a wrong table guess is impossible; view materialisation for the common joins. | 16 |
| HANA vs SQL Server | Two drivers, one interface (`sap/base.py`), automatic selection with per-tenant retry every 120 s. Both dialects now handled in the row-cap bridge. | Which of the two a given customer runs is discovered at runtime, not asked. MSSQL `?`→`%s` substitution is naive (would rewrite a literal `?` inside a string). | A pre-sales checklist that asks SQL-vs-HANA before the call; MSSQL regression fixture. | 8 |
| Service Layer client | Real httpx client: session login, retry/backoff, `PATCH` with `If-Match:*`, master-data update in place, **document writes routed to `/Drafts`** with the numeric `DocObjectCode` (`23` quotation, `17` order, `13` invoice, `22` purchase order) and the draft lifecycle (`Cancel`, `Reopen`, `SaveDraftToDocument`, payment drafts). Cancels never delete. | Never executed against a live Service Layer. Error-code mapping is generic — SAP's `-5002`/`-5005` bodies are shown raw. | Concrete handling for the five errors you will actually hit (series missing, period locked, credit limit, UDF validation, duplicate key), and a mocked-SL test harness. | 20 |
| Auth / permissions | HMAC-SHA256 signed tokens (constant-time compare), roles (`superadmin`/`partner_admin`/`employee`), tenant contextvar, **fail-closed** when the token names an unknown company (this leaked the previous request's tenant before this week), per-tenant `write_enabled`, rate limits (3000 reads / 100 writes per hour), SSRF guard on every tenant host, append-only per-tenant audit JSONL with secret redaction, Fernet-encrypted stored SAP passwords, `admin` login and partner tenancy behind bcrypt. | — | Per-user mapping to B1 authorisations (today: whoever holds the token sees everything the SQL layer returns); token revocation list; SSO. | 32 |
| Answer formatting | `serialize.py` makes every Decimal/date/bytes JSON-safe; `entities.decode_rows` turns `C`→`Customer`, `O`→`Open`; `charts.py` builds chart specs with an "Others" rollup; SSE streams tokens and tool events. | Chart rendering end-to-end in the UI on live data. | A "show me the SQL and the rows" toggle on every answer — this is the single cheapest trust feature you have. | 12 |
| Sandbox CI harness | Offline SQLite sandbox with named anchors (Earthshaker Corporation, Maxi-Teq, A00001–A00003, Printers/Servers groups, Cash in Bank), a schema-version marker that rebuilds stale files, and 64 passing tests (`pytest -q` green after this week's fixes). | Anchor rows carry fixed codes; random generation avoids them, but only because of reserved-code filters added this week. | A nightly job that runs the suite against a seeded sandbox and publishes the scorecard. | 6 |
| Deploy story | One `docker-compose.yml` (backend + frontend, SQLite volume — the dead postgres service and its unused `DATABASE_URL` were removed this week), `Dockerfile` per app, `doctor.py` preflight, `.bat` launchers for a Windows B1 server, `.dockerignore` in both images. | The compose file has not been built and run end-to-end in this workspace. | A one-page install runbook; a signed single-binary or Windows service wrapper; a "no internet" install test. | 16 |
| Config | Every knob env-driven; no baked-in host, no default admin password, loopback-only CORS default; `config.summary()` exposes a `safety` block (writes enabled, any-employee login allowed, bootstrap configured, allowed origins). | — | A `doctor.py` check that prints exactly which SAP ports are reachable and which of SQL/HANA was detected. | 8 |
| Error handling | Distinct `SapDataError` (user-fixable) vs `SapUnavailableError` (transport); SSE keeps the stream alive on tool failure; backend selection retries in the background; migration push returns per-row errors with a row number and a re-push list. | LLM/agent errors are surfaced but not classified (rate limit vs bad key vs context overflow). | An error taxonomy in the UI: "we could not reach HANA" vs "that table has no such column" vs "the model failed". | 12 |
| Offline behaviour | Entire demo runs with zero network and zero customer credentials (`CIRA_DATA_SOURCE=simulator`); every response carries `simulated: true`; the planner degrades to deterministic rules with no LLM key. | — | A visible "SIMULATED DATA" watermark in the UI — currently the flag exists in the payload but a screenshot of the demo looks identical to real data. | 4 |
| Multilingual | Nothing. Only migration column aliases include Hindi (e.g. `ग्राहक नाम`). | — | Hinglish/Hindi question handling, transliteration of customer names, and Indic text rendering in the answer card — this is a genuine differentiator in India/Gulf/Egypt and it is absent. | 40 |

## 1.2 One page a client could read (no jargon)

**What it is.** A box that sits inside your network next to SAP Business One and answers questions
about your own data in plain English or Hindi, then shows you the number, the table it came from,
and the exact SQL. It can also take a messy Excel sheet and turn it into Draft documents inside
Business One for a human to approve.

**What it does not do.** It does not post documents on its own. It never writes directly to the SAP
database. It does not send your data anywhere; the model key is yours and can be a model running on
your own machine. It cannot see anything your SAP user cannot see once per-user mapping is enabled
(that mapping is on the roadmap, not in the box today).

**How data moves.** Question → your server → (a) your SAP database read-only, or (b) your SAP
Service Layer — then the answer comes back to your screen. Nothing is stored except the
conversation, in a file on your server. A log records every write attempt with who/what/when.

**What it costs you to run.** One machine, or one container on the B1 server. No cloud account
required, no Microsoft 365 requirement, no SAP version upgrade.

---

**Do this this week:** run `cd Backend && python -m pytest -q` and paste the pass count into your
notes; then start the app with `CIRA_DATA_SOURCE=simulator` and answer the same three questions
twice — once as an employee token, once as a partner_admin token — to prove tenant separation
before any customer sees it.

---

# 2. Accuracy harness

## 2.1 What it measures now (rewritten this week)

`Backend/tests/accuracy/runner.py` grades eight independent checks per question and prints all of
them; a question PASSES only if every applicable check passes:

| Check | Meaning | Failure is reported as |
|---|---|---|
| `error` | no transport/LLM error | the raw error string |
| `tool` | a query tool was actually called (or the agent said it could not answer) | "no query tool call" |
| `table` | the SQL that executed touched ≥1 expected table | the tables it did touch |
| `column` | it referenced ≥1 expected column | the columns it touched |
| `rows` | ≥ `expect_min_rows` rows (default 1) | row count returned |
| `sql` | optional `expect_sql_regex` / `forbid_sql_regex` | the offending SQL |
| `trap` | hallucination traps: a refusal or an explicit "not in SAP" statement | what it said instead |
| `clarify` | ambiguous questions: the agent must ask, not guess | the guess it made |
| `value` | **new**: the answer's numbers matched values computed independently from the sandbox DB via the question's own `ground_truth_sql` | expected vs seen |

Runner: `python tests/accuracy/runner.py --suite sandbox --out results.json --label run-001`.
Credentials come from `CIRA_HARNESS_TOKEN` or `CIRA_SUPERADMIN_EMAIL`/`CIRA_SUPERADMIN_PASSWORD`
(no personal email is stored in the file any more — it used to contain one, plus the password).
Results are written incrementally, so a crash on question 41 still leaves 40 graded rows on disk.

Gate: `tests/accuracy/ci_gate.py` fails a build below 80% overall, and fails at any value below 100%
on the hallucination bucket. It must also now refuse a run that answered fewer questions than the
suite contains (a stale 20-row `results.json` was the source of the old "8/20" number).

## 2.2 The honest status

| Item | State |
|---|---|
| Questions in the sandbox suite | 60 across 12 buckets (simple 6, aggregate 11, ambiguous 4, hallucination 4, joins 5, time series 5, edge cases 5, master data 5, inventory 5, financials 5, hr 2, service 3) |
| Questions with expected SQL **and** expected result | **0** today. The hook exists; the data does not. |
| Measured accuracy claim you may make | **None.** "unmeasured" is the only truthful word. |
| Language variants measured | 0. There is no Hinglish/Hindi/Gujarati variant of any question. |
| Ambiguous-question scoring | Passes if the agent asks instead of guessing — but nothing checks *which* clarifying question, so a generic "which year?" passes a question about warehouses. |
| Published scorecard | `scorecard.html` exists (score, bucket table, failing list) but has only ever been generated from the old table-name logic. |

## 2.3 Target design (what "50+ real questions per scenario" means)

1. **Value-verified core, per scenario.** For the sandbox, the anchors are already deterministic:
   A00001 on hand = 240; Cash in Bank = 3,271,450.88; Earthshaker open invoices = 2 documents /
   619,150; A00001 ordered by Earthshaker = 200; items at zero on-hand with positive on-order = 1.
   Each of these becomes a `ground_truth_sql` on the question, so `value` is a real comparison, not
   a table-name guess. Target: **25 value-verified questions per scenario** (sandbox, and one
   synthetic "messy" tenant), plus 25 shape-only questions. Hours: 14.
2. **Language variants.** 15 questions × 4 renderings (English, Hinglish, Hindi, and a
   number-in-words variant: "pacchis laakh ka maal" style). Pass = the same SQL *shape* and the same
   value as the English original. Hours: 10.
3. **Ambiguity with an expected clarification.** Each ambiguous question carries
   `expect_clarification_keywords` (e.g. warehouses → "which warehouse", invoices → "which period").
   Hours: 4.
4. **Failure report, not a pass rate.** `scorecard.html` shows: overall, per bucket, the list of
   failing question ids with the first failed check and the offending SQL/value, and a separate
   line for "structural-only" vs "value-verified" accuracy. Hours: 6.
5. **Nightly CI.** A GitHub Actions job that starts the simulator backend, runs the suite, runs the
   gate, uploads `scorecard.html` as an artifact. Hours: 6.

**Cost of the whole harness to "publishable": roughly 40 hours.** Until those 40 hours are spent,
the only sentence you may say to a partner is: "we measure accuracy per tenant and we will show you
the report for yours" — never a percentage.

---

**Do this this week:** fill `ground_truth_sql` on the ten anchor questions (§2.3) and run the
runner twice; if the two runs disagree, the harness is still measuring noise, not accuracy, and
nothing else matters until it agrees.

---

# 3. Excel-to-B1 migration wedge (the actual product)

## 3.1 What exists (built, tested, mounted)

`Backend/migration_routes.py` — `/admin/migration/upload | validate | push | capabilities`, mounted in
`main.py`.

| Capability | Detail |
|---|---|
| File handling | `.csv` (delimiter sniff) and `.xlsx` (read-only, values-not-formulas); typed parsing — dates → ISO, booleans → Y/N, `1250.0` → `1250`; anything else is refused with a 400, never half-parsed |
| Header detection | Header row auto-located below title/report junk; each column report shows the matched SAP field, the match kind (`exact`/`normal`/`fuzzy`/`none`) and `needs_review` — no invented confidence score |
| Mapping | Per-target profiles with aliases (including Hindi), required fields, max lengths, enums; unsupported targets raise 501 rather than importing half a file |
| Validation | Required fields, duplicate keys, enum coercion, number coercion, GSTIN shape check (15 chars) for Indian business partners; output is a column-level report: filled/blank/error counts and per-row errors with the file line number |
| Push | Server re-validates every row (a client cannot smuggle in bad data), reads the current row, and reports **created / updated / unchanged / failed** separately; changed-field lists per row; `failed_rows` come back so only the failures can be re-pushed; content-hash idempotency key + `Idempotency-Key` header replay; writes require the tenant to have `WRITE_ENABLED` |
| Safety | Every write goes through the Service Layer; document-type writes become Drafts; masters (business partners, items) are updated in place because SAP has no draft for master data |

Two real defects fixed this week: the row-cap bridge emitted `LIMIT` on SQL Server (invalid T-SQL,
so every uncapped query failed for the majority of B1 customers), and the re-push diff compared
human-decoded reads (`Customer`) with raw codes (`C`) so every coded column reported a phantom
change on every re-push.

## 3.2 What is missing for v1 (the objects that actually hurt)

| Object | Why it hurts | Path | Hours |
|---|---|---|---|
| Business Partners | Every project starts here; GSTIN/PAN/credit limit/territory are the error-prone columns | Service Layer `BusinessPartners` — built | 0 (done) |
| Items | Item group, UoM, warehouse defaults, tax code | Service Layer `Items` — built | 0 (done) |
| Opening Stock | Balances must land in the right warehouse with the right valuation; wrong = wrong balance sheet on day one | **Either** DTW (`Inventory Opening Balance` object) **or** Service Layer `InventoryOpeningBalances`; recommend DTW for accounts with >5k rows because it is the documented supported path, and Service Layer for small counts where you want a per-row error | 24 |
| A/R open items | Invoices, credit notes and incoming payments must reconcile to the subledger; partial allocation is the classic silent corruption | Service Layer **Drafts** (invoice) + `IncomingPayments` with allocation rows; never a direct table write | 32 |
| DTW file generation | Many partners will not let a tool push; they want the DTW template file to import themselves | Generate the exact `.xlsx`/`.csv` shape DTW expects + a per-column instruction sheet | 12 |
| Human diff-UI approval | The brief's "human diff-UI mapping approval" — today the mapping is returned but there is no side-by-side review screen | Frontend page on top of the existing `headers` mapping response | 16 |
| Self-healing re-push | `failed_rows` exist; no UI button yet | Wire the existing payload to a "fix and re-push failures" action | 8 |

**v1 for Business Partners + Items + Opening Stock + A/R open items: 92 hours** (of which 20 are
the DTW-vs-Service-Layer decision work and 16 the diff UI). That is three focused weeks, or six
weeks at 50% focus.

## 3.3 DTW vs Service Layer, object by object

| Object | Safer via | Why |
|---|---|---|
| Business Partners, Items | Service Layer | Business rules (number series, defaults, UDF validation) run; DTW has known row-count fragility: >~1,000 rows per file is where it starts failing or reporting success while refusing the commit ([SAP note 865191 via r/SAP](https://www.reddit.com/r/SAPBusinessOne/comments/o6cqn0/), [SAP Community](https://community.sap.com/t5/enterprise-resource-planning-q-a/data-transfer-workbench-error/qaq-p/9910363)) |
| Opening Stock | DTW **for large volumes**, Service Layer for small | DTW's Inventory Opening Balance is the documented supported route and is fast; Service Layer gives you a per-row error you can show a human |
| A/R / A/P open items | Service Layer (Drafts) | Allocation, tax and credit-limit logic must run; DTW cannot import past closed activities and gives blank logs when it fails ([Appseconnect](https://www.appseconnect.com/advantages-and-limitations-of-data-workbench-in-sap-business-one-data-migration/), [sap-business-one-tips](https://www.sap-business-one-tips.com/en/data-not-imported-and-detailed-log-screen-blank-on-data-transfer-workbench/)) |
| Anything already posted | Neither | Corrections go through a new document, never an edit |

---

**Do this this week:** take one real (or synthetic) messy sheet with three deliberately broken
rows — a bad GSTIN, a duplicate customer code, a blank name — and run it through
`upload → validate → push`; send the validation report to one partner you already know and ask
only: "would your accountant sign off on this report?"

---

# 4. Countries: A (start now) / B (3–9 months) / C (never)

Scoring: 5 = best. Partner count = number of B1-VAR firms reachable, not general SAP firms.
"Buy add-ons" = evidence partners resell third-party add-ons. English + IST = how much of the
selling day overlaps yours. Remote install = willingness to let a vendor install over a screen
share. GDPR/residency = does client data on your laptop create a legal problem. Payment friction =
how hard it is for a small Indian company to get paid.

| Country | Partners | Buys add-ons | Ticket | English | IST-friendly | Remote OK | Residency | Payments | Score | Tier |
|---|---|---|---|---|---|---|---|---|---|---|
| India | 5 | 5 | 2 | 5 | 5 | 5 | 4 | 5 | **36** | **A** |
| UAE | 4 | 5 | 4 | 5 | 5 | 5 | 4 | 4 | **36** | **A** |
| Saudi | 4 | 4 | 5 | 4 | 5 | 3 | 3 | 4 | **32** | **A** |
| UK | 4 | 4 | 4 | 5 | 3 | 4 | 2 | 4 | **30** | **A** |
| USA | 5 | 4 | 5 | 5 | 2 | 3 | 2 | 4 | **30** | **A** |
| Israel | 3 | 4 | 4 | 5 | 3 | 3 | 3 | 4 | **29** | B |
| Australia | 4 | 4 | 4 | 5 | 4 | 3 | 3 | 3 | **30** | **A (cheap entry)** |
| Singapore | 3 | 4 | 4 | 5 | 4 | 4 | 3 | 4 | **31** | **A (small market)** |
| Netherlands | 4 | 4 | 4 | 5 | 3 | 3 | 2 | 4 | **29** | B |
| Poland/Romania/Czech | 3 | 3 | 3 | 4 | 3 | 3 | 2 | 4 | **25** | B |
| DACH | 4 | 4 | 5 | 3 | 2 | 2 | 2 | 4 | **26** | B (language wall) |
| Italy | 3 | 4 | 3 | 3 | 2 | 2 | 2 | 4 | **23** | B |
| Spain/LatAm (MX/BR/CO) | 4 | 3 | 3 | 3 | 1 | 3 | 2 | 3 | **22** | B (timezone kills it) |
| South Africa | 3 | 3 | 3 | 5 | 4 | 4 | 3 | 3 | **28** | B |
| Malaysia/Vietnam/Philippines | 3 | 3 | 2 | 4 | 3 | 4 | 3 | 4 | **26** | B |
| Egypt | 3 | 3 | 2 | 4 | 4 | 4 | 2 | 3 | **25** | B |
| Turkey | 3 | 3 | 3 | 3 | 4 | 3 | 2 | 3 | **24** | C (currency + language) |
| Gulf ex-UAE/Saudi (Qatar/Oman/Kuwait) | 2 | 4 | 4 | 5 | 5 | 4 | 3 | 4 | **31** | B (via UAE partner) |

**A-set to work in 60 days: India (proof + reference), UAE (best money-to-effort ratio), Australia
(via one partner, English, IST+5), Singapore/Malaysia (same partner as UAE often), UK (one
London-based B1 VAR), Saudi (only via a Qualifying/Resident partner — you cannot invoice directly
without a local presence in practice).**

## 4.1 A-country partner targets (company-level verified; named people where public)

**Read the method, not just the list.** Every entry below came from the partner's own site, its
SAP Partner Finder profile or a published leadership page. Contacts marked ✔ have a named,
role-verified person. Contacts marked ◻ mean the company is verified but the decision-maker must be
confirmed in a 20-minute pass (method below) — I will not print a name or a LinkedIn URL I have not
seen.

### India (verify on [partnerfinder.sap.com](https://partnerfinder.sap.com))

| # | Firm | Website | Named contact (verified) |
|---|---|---|---|
| 1 | Cogniscient Business Solutions | cogniscient.in | ✔ Rajeev Agarwal, CEO & Founder; Parul Agarwal, Director & Co-Founder ([about](https://www.cogniscient.in/about-us/)) |
| 2 | TEKROI Pvt Ltd | tekroi.com | ✔ Venkata Siva Reddy Polu; Anitha Vennapusa (founders) ([profile](https://tekroi.com/sap-business-one-partner-in-india/)) — also your most direct competitor |
| 3 | Uneecops Technologies | uneecops.com | ◻ |
| 4 | SoftCore Solutions | softcoresolutions.com | ◻ |
| 5 | Praxis Info Solutions | praxisinfosolutions.com | ◻ |
| 6 | Accelon Technologies | accelon.in | ◻ |
| 7 | Sterling Team (India) | sterling-team.in | ◻ |
| 8 | Beone Solutions (India) | beonesolutions.com | ◻ |
| 9 | Silver Touch Technologies | silvertouch.com | ◻ |
| 10 | ECS Biztech | ecsbiztech.com | ◻ |
| 11 | Megatherm ERP | megathermerp.co.in | ◻ |
| 12 | Elevra Tech | elevratech.com | ◻ |
| 13 | Avaniko | avaniko.com | ◻ |
| 14 | MegatechVerse | megatechverse.com | ◻ |
| 15 | Sapphire Systems (India) | sapphiresystems.com | ◻ |
| 16 | Inecom Business Solutions | inecom.co.in | ◻ |
| 17 | SAP Stack partner network listings | sapstack.com | ◻ (source of many names — treat as a lead list) |
| 18 | Bodhtree Consulting | bodhtree.com | ◻ |
| 19 | SISL Infotech | sisl.co.in | ◻ |
| 20 | Trigyn / others via Partner Finder | partnerfinder.sap.com | ◻ |

### UAE

| # | Firm | Website | Notes |
|---|---|---|---|
| 1 | WMS Middle East LLC | wmsspl.com | SAP Gold; Dubai ([site](https://wmsspl.com/)) |
| 2 | Pinnacle Computer Systems | pinnacleuae.com | B1 Gold, SME focus |
| 3 | Seidor UAE | seidor.com | Platinum; multi-country |
| 4 | Indus Novateur | indusnovateur.com | B1 + ByD, three emirates |
| 5 | Inecom (DMCC) | inecom.co.in/uae | B1-only; UAE + India ([site](https://inecom.co.in/uae/)) |
| 6 | Emerging Alliance | emerging-alliance.com | B1 Gold, Sharjah; 1,000+ licences sold claim |
| 7 | Zyple / VC ERP / Inteliwaves / SID / SmartNet / NijaTech / PBSS | see [Azdan directory](https://www.azdan.com/blog/best-erp-companies-in-uae-2026) | company-level verified, contacts to confirm |
| 8–20 | UAE B1 VAR list via [softwaresuggest](https://www.softwaresuggest.com/sap-partner/uae) and SAP Partner Finder | — | 20 is reachable; each needs the 20-minute pass |

### Australia / Singapore / UK / Saudi
Same treatment: Australia — Sapphire Systems, Decision Inc., Brennan, Klugo, Fusion5, Endeavour
Solutions, Dyflex, Mantel Group (B1 arms where applicable); Singapore/Malaysia — Uneecops SEA,
Beone, Datum, B1 specialists listed on Partner Finder; UK — Sapphire, Codestone, InCloud, Pinnacle,
Frontline Consultancy, Tenzing; Saudi — only approach through a partner with a local CR (Seidor,
WMS, local Riyadh VARs). All ◻ — company verified, person to confirm.

## 4.2 The 20-minute method (how you turn ◻ into a name)

1. Open the firm's LinkedIn company page → People → filter by "Founder/Owner/Partner/Director/CEO"
   → note the name and headline. That is your decision-maker, reaching them *in* the company page
   context (not their personal inbox) is normal B2B practice.
2. Cross-check the firm's site "About/Leadership" page for the same person (cheap verification).
3. If the firm has no leadership page or LinkedIn people list, it is a 3–15 person shop: the
   decision-maker is the owner, and the fastest channel is the WhatsApp/sales number on their
   contact page.
4. Never buy an email list for this. One named human + one specific question beats 200 scraped
   addresses, and a bought list is also a DPDP problem.

---

**Do this this week:** build a 40-row sheet — 20 India + 20 UAE — with firm, website, named person
(if found), and the *one* thing you will send them; then send 40 first-touch messages (see §7) and
record replies. Fewer than 4 replies in 14 days means the list or the message is wrong, not the
market.

---

# 5. Pricing, packaging, and the money mechanics

## 5.1 Competitor price anchors (use these in every quote)

| Product | Price | Source |
|---|---|---|
| TEKAI (TEKROI) | ₹5,000/company/month India; $150/company/month global; BYO AI subscription; no free tier | [tekroi.com/faqs](https://tekroi.com/faqs/) |
| TEKROI cloud packages (incl. TEKAI) | ₹79,999 / ₹1,14,999 / ₹1,49,999 per month for 10 / 15 / 20 users | tekroi.com partner pages |
| SAP B1 professional user licence | $3,000–3,500 perpetual; cloud $100–150/user/month; maintenance 17–22%/yr | [multientityaccounting](https://multientityaccounting.com/sap-business-one-pricing-multi-entity-finance/) — vendor-compiled, treat as indicative |
| B1 add-ons generally | $1,000–10,000 one-time + $2,000–20,000/yr maintenance | same |
| B1 implementation project | $25k–300k | same |
| XL-Importer (migration) | ~$2,500 per B1 licence server; journal/budget only | [b1developers](https://www.b1developers.com/XLImporter) |
| Codeless Platforms B1 connector | £350–$4,200/month | [codelessplatforms](https://www.codelessplatforms.com/connectors/sap-business-one-integration/) |
| B1UP (Boyum) | paid per-user add-on via SAP partner; 20-day trial; price not public | [Boyum FAQ](https://support.boyum-it.com/hc/en-us/articles/204997957-FAQ-General) |
| SAP ICC certification (if you ever certify) | from ≈€3,000 | [SAP](https://www.sap.com/partners/partner-program/certify-my-solution.html) |
| SAP PartnerEdge | Ecosystem/Build entry tier free; full Build ≈€2,000/yr | [AvoTechs](https://avotechs.com/blog/become-sap-build-partner/); r/SAP "2k euro minimum annual fee" |

## 5.2 The three commercial shapes

| Shape | Who pays | Price | Why they say yes | Risk to you |
|---|---|---|---|---|
| Direct | The B1 end client | ₹15,000–25,000/month (India) / $250–400/month (Gulf/UK/AU) for read + migration module, ex-GST | No procurement, no MSA, cancel any month | Solo support load; you are the only person they call |
| White-label (recommended) | The partner, per their client | Partner pays ₹10,000/company/month, bills their client ₹25,000–40,000/month under their own brand | The partner keeps the logo, the client and the margin; you are invisible and non-threatening | Partner must be trained; they can leave you once they understand it |
| Partner-resells (unlimited projects) | The partner, flat | ₹40,000/month per partner office, unlimited end clients (India/Gulf); $600/month outside India | Predictable; the partner can deploy before they have a signed client | Usage grows; put a fair-use clause (e.g. 25 tenants) |

**Decision on the migration tool alone** (the brief's three options):
- ₹10–40k/month unlimited projects → best for a partner with a project pipeline; hardest to sell to
  a partner with two projects a year.
- ₹5–15k per migration → easiest to say yes to for a one-off project, but it teaches the partner to
  treat you as a contractor, not a product, and you carry the delivery risk every time.
- Per-implementation licence → needs a contract, legal review and a procurement conversation; a
  15-person firm will not do this for a ₹5k product.

**Pick: ₹15,000 per migration for the first three partners; convert to ₹25,000/month white-label
after the second successful migration.** Reason: the first sale must be a cash decision the owner
can make alone without a signature.

## 5.3 Minimum commitment, currency, terms

| Item | Recommendation |
|---|---|
| Minimum term | 3 months prepaid for the read tier; migration one-off is paid before the file is processed |
| Currency | INR for India; USD for everyone else (Gulf clients will pay USD; UK/AU clients will pay USD before they will pay INR, and a USD invoice avoids their FX desk) |
| Setup | ₹25,000 one-time white-label setup (branding, tenant, 1 template) — waive for the first two partners in exchange for a case study |
| AMC | Included in the monthly price. Do not sell a separate AMC as a solo operator — it is an unbounded promise |
| Payment rails | Stripe (INR + USD, 2% domestic / ~3% international) + Wise Business for USD/GBP/AUD transfers; PayPal only if a client insists (fees are the worst of the three and chargebacks are hostile). UNVERIFIED: exact current fee schedules |
| Indian export invoicing | You invoice in USD/GBP as an export of services under LUT (Letter of Undertaking) so you do not charge IGST; you still report it in GSTR-1 as export. You need an FIRC/FIRA from the bank to prove the inward remittance for GST/RBI purposes. Simplest legal shape: proprietorship with a current account + LUT, or a Pvt Ltd if you take a partner. UNVERIFIED: exact LUT/BRC documentary requirements — confirm with a CA before the first invoice (budget ₹5,000–10,000 for the CA's time) |
| GST | Indian customers: 18% GST on top. Foreign customers: zero-rated export, LUT on file |

## 5.4 The margin story, with arithmetic — a real 40-user manufacturer

Assumptions stated plainly: 40 named SAP users, ~15 of them touch order entry; order entry is
10 minutes per sales order; 30 orders/day; loaded cost of the order-entry clerk ₹250/hour.

| Line | Value |
|---|---|
| Manual order entry cost/day | 30 orders × 10 min = 5 hours × ₹250 = **₹1,250/day** |
| Annualised (250 working days) | **₹3,12,500/year** of clerk time on typing |
| Errors and rework (industry rule of thumb 3–5%; use 4%) | ₹12,500/year, plus the customer-trust cost |
| Migration + read tier you charge | ₹15,000 once + ₹15,000/month = ₹1,95,000/year |
| Partner's gross margin if they resell at ₹30,000/month | ₹3,60,000 revenue − ₹1,80,000 to you = **₹1,80,000/year margin per client**, 50% |
| Client's payback | If order entry drops 50%, they save ₹1,56,250/year plus error costs — the ₹3,60,000 they pay does not pay back on typing alone. Sell the *migration* and the *reporting* (closing the month in 2 days instead of 6), not typing speed |

Be honest with the partner: at a 40-user manufacturer, the ROI is real but not from labour
arbitrage alone. The buyer is the owner who wants answers without waiting for a report.

---

**Do this this week:** print one quote — white-label ₹25,000/month + ₹25,000 setup, 3-month minimum,
USD for non-India — and send it to one partner with no explanation attached. Watch what they ask;
the first question tells you what the whole price page should say.

---

# 6. Outplay table

| Competitor | What they have | Price | GTM | Weakness you can name out loud | You win / you don't |
|---|---|---|---|---|---|
| **TEKAI (TEKROI)** | Grounded NL→SQL/MCP over the customer's own DB, model-agnostic, read-only by default, live in a day, one of four GenAI B1 solutions in SAP's own AI Partner Innovations Playbook | ₹5,000/company/mo India; $150 global; BYO model subscription | Direct + partner, Hyderabad, 350+ implementations, SAP PartnerEdge | It is a *read* product; anything beyond scoped interfaces/write actions is "quoted on a demo call". No migration wedge, no white-label, no per-client measured-accuracy report | **You don't beat them on read-only Q&A in India.** You beat them where the buyer wants their own logo on it (partner), where data cannot leave the LAN (they are cloud-hosted by default), and on Excel→B1 migration |
| **SAP native: Ask AI + AI-assisted UDQ** | Contextual answers on the Web Client screen you are already on, reusable AI templates, UDQ generates validated SQL | Not separately priced, but requires FP 2608 + Web Client + BTP enterprise account with AI Core/GenAI Hub consumption — i.e. not free ([softcore](https://softcoresolutions.com/blog/ai-in-sap-business-one/)) | Bundled by SAP | Requires a version upgrade, the Web Client, and a SAP cloud subscription; SQL Server customers and on-prem-only customers are locked out; zero vernacular; you cannot white-label it | **You win on "no FP 2608 upgrade, no Web Client, no BTP, works on the version you run today, on-prem".** Say this in one sentence and stop |
| **SAP MCP Server (FP 2608 sample)** | Official sample code turning Service Layer OData into MCP tools: CRUD, order→delivery→invoice chaining, payment posting, human-in-the-loop elicitation, personal-data redaction; needs FP 2608 + SLD + IAM-Keycloak + OAuth2 ([SAP Help](https://help.sap.com/docs/SAP_BUSINESS_ONE/bb89a9939c294f14a7f532f7e76ade9e)) | Free sample code, you run it | SAP direct to partners | It is a *sample*: no UI, no mapping, no validation, no Excel story, requires an OAuth2/Keycloak stack most 5-person B1 partners cannot operate | **You don't out-engineer it; you out-package it.** Your pitch: "this is the messy-edge version of what SAP will ship in three years" |
| **B1 iMapper (Reality Solutions)** | — | — | — | **UNVERIFIED.** Two searches found no vendor page; do not put its features or price on a slide. Ask a partner what they use instead | Unknown — leave the row blank in customer conversations |
| **Boyum B1UP / Boxy** | The de-facto UX layer in B1 shops: forms, validations, batch updates, mobile-ish widgets, 20-day trial, sold per user through SAP partners | Paid, price not public | Partner channel, decades of trust | Not AI, not natural language; per-user licence cost that the client notices; nothing for Excel-to-B1 migration quality | **You don't compete.** You co-exist and, ideally, get installed on the same machines |
| **Jet Reports / Theobald** | Financial reporting inside Excel; huge installed base; partner-loved | Per-user, published on request ([Jet Reports](https://www.jetreports.com/pricing/), [Theobald](https://theobaldsoftware.com/)) | Partner + direct | They report; they do not answer questions in words, and they cannot take a messy sheet *into* B1 | Don't fight. If a client has Jet, position CIRA as the question layer above it |
| **Generic text-to-SQL (Querio, Defog, Vanna, DB-GPT, Genie, Cortex Analyst)** | Query generation, benchmarks, and in the case of Genie/Cortex, managed deployment | Freemium → $20–50/user/mo for hosted tools | Self-serve, developer-first | None of them know B1's table names, code maps (`O`=Open, `C`=Customer), number series, or that a document write must become a Draft. None carry SAP licence-risk guidance | **You win on the 400 tables and the codes, not the SQL.** Their demo looks better on a clean schema; yours works on B1 |
| **Tally / Zoho AI in India** | Zoho Books ₹899–9,999/mo tiers with built-in IRP e-invoicing, GSTR filing via GSP, GSTR-2B auto-reconciliation; TallyPrime Silver ₹600/mo or ₹18,000 one-time, Gold ₹1,800/mo or ₹54,000; ClearTax GST ₹14,999–29,999/yr ([patronaccounting](https://www.patronaccounting.com/blog/zoho-books-guide-indian-businesses-2026)) | ₹600–10,000/month | Volume, resellers, brand | They are the destination for companies *leaving* or *avoiding* ERP; they do not improve an existing SAP B1 install, and a 40-user manufacturer is not migrating to Tally | **You don't win against them and you do not need to.** Your buyer already owns SAP B1 and will not replace it |

## 6.1 The three sentences a partner believes

> "It runs on the SAP Business One version they already own — no FP 2608 upgrade, no Web Client,
> no BTP subscription, no Microsoft 365."  "It speaks the way your client's accountant actually
> types, and it keeps the data inside their LAN, on your infrastructure, under your logo."
> "It turns their Excel chaos into Draft documents a human approves, and shows a measured accuracy
> report per client — not a marketing percentage."

## 6.2 Is an accommodation play clever or self-defeating?

**Selling migration tooling to a competitor like TEKROI as a component they lack** — and building
the read tier as a TEKAI-adjacent product — is clever *only* in one specific form: you sell them a
component they cannot get elsewhere (human-approved Excel→B1 draft generation with a per-row error
report), it is invisible to their customers, and the contract is non-exclusive so you keep selling
it yourself.

It becomes self-defeating the moment (a) you white-label your read tier to them, because their
brand is stronger and your logo never reaches a customer; (b) they can rebuild the component in a
quarter — which they can, it is 90 hours of work, so your only durable protection is that you own
the messy-sheet corpus and the per-client accuracy history, not the code; or (c) you sign an
exclusivity clause, which converts your product into their feature.

Judgement, plainly: **sell the migration component to competitors, never the question-answering
layer.** The question layer at ₹5,000/company is a feature; the migration tool with a validation
report an accountant signs is a deliverable with a completion date, and deliverables can be billed
to anyone — including the firms that would otherwise be your competition.

---

**Do this this week:** write the component one-pager (what it does, what it needs, what it costs,
what it cannot do) and send it to two B1 partners as a *supplier* introduction, not a sales pitch.

---

# 7. Selling motions

## 7.1 The sequence (one partner, five touches, 14 days)

| Day | Step | What you do | What you must leave with |
|---|---|---|---|
| 1 | Warm-up | Send the component one-pager + one screenshot of a validation report (no client name) | A reply, or a second touch scheduled |
| 3 | Discovery (20 min) | Ask, in this order: how many B1 clients, how many have SQL vs HANA, how do they migrate masters today, what breaks most often, who signs off on a go-live, what would make them try a tool on one client | The name of the one client they would pilot on |
| 7 | Demo (4 min, §7.2) | Screen share, their data or the sandbox — never a slide | A question that means they are imagining it in their pipeline |
| 9–10 | Pilot (14 days, §7.5) | Three named questions, an accuracy bar, six hours of your time, then a signed note | A written result: pass or fail, their words |
| 14 | Close | Quote, 3-month minimum, white-label | Payment or a dated no |

## 7.2 The 4-minute demo script (say it exactly like this)

1. **0:00–0:30 — the pain.** "Your client sends a 4,000-row Excel of customers. Today someone
   re-types it, or runs DTW and finds out at midnight that row 2,847 killed the file."
2. **0:30–1:30 — upload and the report.** Show the messy sheet going in, then the column report:
   "27 columns matched, 3 need your decision, 41 rows failed — here are the line numbers and the
   reason."
3. **1:30–2:30 — the fix loop.** Fix one bad GSTIN in the sheet, re-push *only* the failed rows,
   show created/updated/unchanged/failed changing. "Nothing is posted. These are Drafts your
   accountant approves inside B1."
4. **2:30–3:30 — one question in words.** Switch to chat: ask "what's the stock of A00001" — show
   the number, the table, and the SQL. "This is the same engine, read-only, on their own server."
5. **3:30–4:00 — the ask.** "Give me one client and three questions. Two weeks. If the numbers are
   wrong, you'll know before your client does."

## 7.3 First-touch copy (English — adapt, don't translate)

**Email (subject: "Excel → B1 drafts, with the failure list your accountant can read")**

> Hi <name>, I build an Excel-to-Business-One tool that turns a messy sheet into Draft documents
> in B1 and gives a per-row failure report — not a "0 errors" message that hides 41 skipped rows.
> It runs on the B1 version your client already has: no FP 2608, no Web Client, no cloud account.
> If you have one client with a messy customer or item sheet, I'll run it free on three of your
> questions and send you the validation report. 20 minutes this week?
> — Aryan, <phone>, <site>

**LinkedIn (connection note, under 300 chars)**

> B1 partners in <city>: I built Excel→B1 draft migration with a per-row failure report, on-prem,
> no FP 2608 needed. Happy to run it free on one messy sheet you already have.

**WhatsApp (only after contact exists)**

> Hi <name> — Aryan here, I do Excel→SAP B1 migration tooling. Can I send you a 1-page sample
> validation report from a messy customer sheet? No call needed yet.

**Localisation (same meaning, not a machine translation):**
- **Hindi/Hinglish (India):** "Sir, Excel se B1 me customer/item upload karta hoon — jo rows fail
  hoti hain unki list milegi, chupaya nahi jayega. Aapke ek client par free chala ke dikhaun?"
- **Gulf/English (UAE/Saudi):** drop "Sir", add "no data leaves your client's server" in the first
  line — that is the first objection in that market.
- **UK/AU:** "audit-friendly", "your client's accountants sign off the report" — lead with control,
  not speed.
- **Singapore/Malaysia:** mention GST/SST codes and multi-currency up front.

## 7.4 Two objection handlers per country

| Objection | India | UAE/Saudi | UK/AU | Singapore/MY |
|---|---|---|---|---|
| "SAP ships this free" | "Ask AI needs FP 2608 + Web Client + a BTP subscription. Your client's version is older; this runs today." | "Ask AI is cloud; your clients' data policy says no. This runs inside their server room." | "Free in a future release is not a plan for a go-live in six weeks." | "Same — and it needs the Web Client app set, which most of your SME clients have not deployed." |
| "We already use TEKAI" | "Then keep it for Q&A. I do the part TEKAI is not: Excel→Drafts with a failure list. I can even be a component under your TEKAI deployment." | "Fine — this is the migration half; two vendors, two invoices, no conflict." | "Ask them to white-label it under your logo; if they won't, that's the gap I fill." | "Different problem: they answer questions, I move data with an audit trail." |
| "Data can't go to cloud" | "It doesn't. Local container, your model key, or a model on your own box." | "Same — and we can run with no internet at all after install." | "Data stays in your VPC/host; the model key is your client's." | "On-prem or your client's cloud tenancy — your choice." |
| "What if it lies?" | "It shows the SQL and the table for every number, and you get the measured report per client. If we can't measure it, we don't quote it." | Same + "every write is a Draft; a human clicks approve in B1." | Same + "audit log of every query and write attempt, exportable." | Same. |
| "Send me a proposal" | "Which client and which sheet? I'll run it first, then the proposal is one page with real numbers." | Same | Same | Same |
| "Send free work" | Cap it: 3 questions, 6 hours, 14 days, written accuracy bar. Anything beyond is a paid discovery day (₹15,000). |

## 7.5 The 14-day pilot (exactly this, every time)

| Element | Definition |
|---|---|
| Questions | 3 named questions, written down and signed off before you start (e.g. "open invoices for <customer>", "stock of <item>", "top 5 customers by sales this year") |
| Accuracy bar | Every number must be reproducible in SAP's own UI by their accountant; the pilot passes at 3/3 reproducible, or a written explanation of each miss |
| Your time | Capped at **6 hours** including install. Publish the cap — it is what makes the pilot feel safe |
| Install | Under 1 hour, on their machine, screen-shared, no VPN |
| Output | One page: question, answer, the row in SAP that proves it, and what you could not answer |
| Exit | Pass → quote. Fail → you write the failure and walk; no invoice, no argument |

## 7.6 Effortlessness-to-buy checklist (build toward this)

Install <1 hour · single compose or one binary · no VPN · per-tenant config · self-serve onboarding ·
1-page threat model · 1-page pilot scope · a real invoice in the currency they pay in · a phone
number that a human answers.

---

**Do this this week:** send the §7.3 email to 20 India and 20 UAE partners, and put the date in a
calendar entry labelled "20 replies or re-list".

---

# 8. Build order — 90 days, ordered by rupees per hour

Ranking is revenue-impact ÷ hours, not elegance. "Fake honestly" = a mock a customer can see
through, clearly labelled, that buys time (never a fake number, never a fake integration).

| Rank | Work | Hours | Revenue link | Build / Cut / Fake honestly |
|---|---|---|---|---|
| 1 | **Authorization + audit layer before any write** (§8.1) | 32 | Blocks the first paid migration; without it you cannot legally touch a client file | **Build now** |
| 2 | Migration: Opening Stock + A/R open items | 56 | Every go-live needs these; ₹15k–40k per migration | **Build now** (this is the wedge) |
| 3 | Migration: DTW-ready file output | 12 | Lets you sell to partners who will not let a tool push | **Build** |
| 4 | Failed-row re-push UI + mapping approval screen | 24 | Turns a demo into a workflow; partners pay for the workflow | **Build** |
| 5 | Per-client accuracy report (from §2) | 40 | The trust asset; also the only honest marketing number | **Build in parallel** |
| 6 | Value-verified ground truth for the sandbox suite | 14 | Unlocks #5 | **Build** |
| 7 | Client-readable "what it does" page + threat model | 8 | Removes the security objection in one page | **Build** |
| 8 | White-label (logo, colour, domain per tenant) | 16 | Unlocks the partner-resell price (2–3× direct) | **Build (small)** |
| 9 | Per-user B1 authorisation mapping | 32 | Needed before any multi-user customer beyond 3 people | **Fake honestly**: partner-admin token + a written "single-role pilot" note until it ships |
| 10 | Hindi/Hinglish question handling | 40 | India differentiator; not required for the first 3 paying partners | **Cut** in the first 90 days |
| 11 | Multi-LLM BYO key UX (local model config screen) | 12 | Removes "data can't go to cloud" | **Build (small)**: the backend supports it; add the settings screen |
| 12 | Chart parity with the Web Client | 20 | Cosmetic | **Cut** |
| 13 | Mobile/native app | — | None at this stage | **Cut** |
| 14 | SAP ICC certification | — | €3,000+ and months; not needed to sell a service | **Cut** until a partner demands it |
| 15 | SSO / SAML | 24 | Enterprise-only | **Cut** |

## 8.1 The authorization + audit layer (must exist before the first write)

| Requirement | Status | Hours |
|---|---|---|
| Per-user permissions mapped to B1 authorisations | Not built — roles today are app roles (`partner_admin`, `employee`), not B1 authorisation groups | 24 |
| Idempotency keys on every write | **Built** (content hash + `Idempotency-Key` header, replay returns the first result) | 0 |
| Immutable audit log | **Built** (append-only per-tenant JSONL, redacted secrets); still missing: hash chaining so a deleted line is detectable | 6 |
| Cancel/return, never delete | **Built** for drafts (`Cancel`, `Reopen`); no delete path exists at all | 2 |
| Kill switch | Partial: per-tenant `WRITE_ENABLED` gate returns 403 for every write route | 4 |
| Rate limits | **Built** (3000 reads / 100 writes per hour per tenant, in-process) | 4 |
| Sandbox-only mode | **Built** (`CIRA_DATA_SOURCE=simulator`, every payload marked `simulated`) | 0 |
| One-click stop for the operator | Not built (a global read-only switch that does not require a restart) | 4 |

Total to be write-ready for a stranger's ERP: **~44 hours**, of which 24 are the B1 authorisation
mapping. Until that mapping exists, every pilot runs under a single explicitly-created B1 user.

---

**Do this this week:** implement the kill switch and hash-chain the audit log (10 hours), then write
the number "44 hours to write-ready" next to the first migration quote so it is priced in, not
discovered.

---

# 9. Legal and commercial (solo operator, India)

| Question | Answer | Why / cost |
|---|---|---|
| Pvt Ltd vs LLP vs nothing | **Start as a proprietorship** with a current account + GST + LUT for exports. Move to a **Pvt Ltd** only when (a) a partner wants equity, (b) a client refuses to contract with an individual, or (c) you cross ~₹20–30L/year revenue | Incorporation cost ₹8,000–15,000 + ₹15,000–30,000/yr compliance (CA); an LLP is cheaper to maintain but harder to raise against. UNVERIFIED: current government fee schedule |
| When is a legal entity mandatory | The moment you take money from a foreign client through a bank that asks for an IEC/LUT, or the moment you sign a contract with a liability clause. Not before | — |
| Liability cap | Cap at **fees paid in the preceding 3 months**, exclude indirect/consequential loss, and state that the client is responsible for approving every document inside B1 | A ₹15,000/month contract must not carry an unlimited ERP-corruption claim |
| T&Cs before touching writes | Yes — a 2-page service agreement: scope, the pilot cap, the liability cap, data handling, the fact that all writes are Drafts, and the client's responsibility to approve | Template + one CA/lawyer review: ₹10,000–25,000 one-time |
| Client-data protection wording | "Data is processed on infrastructure you nominate. The model provider is configured by you with your key; no client data is used to train any model; no client data leaves your network unless you configure a cloud model." Put it in the contract, not just the website | — |
| GDPR / DPDP when client data reaches your laptop | Assume any real client file is personal data. Rule: **never** keep a client file on your laptop beyond the session; work on their machine over a screen share, or on your sandbox with synthetic data. If you must take a file, delete it after the run and record the deletion | DPDP Act 2023 obligations for a data processor are lighter if you never retain; GDPR applies if the client is in the EU and you process on your own device |
| Insurance | Professional indemnity / tech E&O for a solo operator in India is available but thin and expensive relative to your revenue (quotes commonly ₹25,000–75,000/yr for small limits). `UNVERIFIED` — get two quotes before quoting a client that asks | Until then, cap liability in the contract |
| Support SLA you can actually keep | Email/WhatsApp, **next business day**, 09:00–19:00 IST, no 24×7 promise, no phone SLA for the first year. Put the response target in writing | A solo operator who promises 4-hour response loses the client in week three |

---

**Do this this week:** write the 2-page service agreement with the 3-month liability cap and the
"all writes are Drafts" clause, and get one CA quote for LUT/FIRC handling.

---

# 10. Risks and kill criteria

| # | How it dies | Probability | Early signal | Kill criterion / mitigation |
|---|---|---|---|---|
| 1 | **No distribution.** SAP B1 is partner-only; you have no partner and no brand | High | Fewer than 4 replies from 40 targeted messages in 14 days | **Kill the current list and message, not the product**: re-cut the list to 10-person firms where the owner answers WhatsApp, and change the first line to the migration pain |
| 2 | **TEKAI (or SAP's own MCP/Ask AI) makes the read tier free** | Medium-high (12–24 months) | A partner says "TEKAI already does this" twice in a row | Pivot entirely to the migration + write layer, which is workflow, not model output. **Kill criterion: if 3 of your first 5 conversations say the Q&A is already solved, stop building read features** |
| 3 | **The migration tool breaks a client's data** and the partner drops you | Medium | A re-push produces a difference the accountant cannot explain | Never write outside Drafts; always print created/updated/unchanged/failed; hash-chain the audit log. **Kill criterion: one unexplained data difference = stop all live pushes, refund the month, do a public post-mortem with that partner** |
| 4 | **No paying tenant in 30 days** | High (as a solo, unfunded operator) | Zero paid after 30 days of selling | **Stop building features entirely; sell only.** Ship nothing new until the first invoice is collected |
| 5 | **You burn out selling to strangers in timezones you are awake for** | Medium | Two weeks with no demo | Narrow to India + UAE only for 60 days; the A-list exists precisely so you stop spreading thin |

## 10.1 Falsifiable checkpoints (metric + date)

| By | Metric | If missed |
|---|---|---|
| Day 14 | 40 targeted first-touch messages sent; **≥4 replies** | Rebuild the list and the message; do not "send more" |
| Day 21 | **2 demos delivered** | The pitch is wrong — record the demos and rewrite the first 30 seconds |
| Day 30 | **3 pilots started** (3 questions, 6 hours each) | Offer the pilot free with no install fee; if still zero, the buyer is wrong (go up-market to larger partners) |
| Day 45 | **1 paying tenant** (even ₹5,000) | Stop building; sales only, 6 hours a day |
| Day 60 | **₹40,000/month recurring** or **one paid migration at ₹15,000+** | Take a contract job to fund 3 more months; keep the product alive on weekends |
| Day 90 | **2 paying partners, ≥₹75,000/month** or one migration + one read tenant | Re-evaluate honestly: component sale to competitors (§6.2) is the fallback, not a rescue |

---

**Do this this week:** put the Day-14 number (4 replies) on the wall, and write down what you will
do if it is 0 — before you send anything.

---

# 11. One-page 90-day roadmap

Owner: you. One number per week. Revenue checkpoints in bold.

| Week | One number | Work | Sales |
|---|---|---|---|
| 1 | 40 messages sent | Fix the harness (ground truth on 10 anchors), kill switch, audit hash chain | Build the 40-row India+UAE list; send the first 20 |
| 2 | ≥2 replies | Opening Stock path (DTW file + validation) | Send the other 20; book 2 demos |
| 3 | 2 demos done | A/R open items via Drafts | Run demos; ask for the pilot client each time |
| 4 | 3 pilots started | Mapping approval UI + failed-row re-push | Start pilots; instrument the 6-hour cap |
| 5 | 1 pilot passed | Value-verified suite (25 questions) | Convert the passed pilot to a quote |
| 6 | **First invoice raised** | White-label branding + settings screen | Send quotes to the other two pilots |
| 7 | ₹5,000–15,000 collected | Threat model + client one-pager | Ask every partner for a second introduction |
| 8 | 1 paying tenant | Per-client accuracy report | Follow up all non-repliers once, with the report attached |
| 9 | 2 demos/week running | Opening-stock dry runs on partner data | Push for a migration project, not just a read tenant |
| 10 | 1 signature (letter of intent) | Hardening: error taxonomy, doctor output | Price review — raise the white-label price if it was never questioned |
| 11 | **₹15,000+ from a migration** | Multi-tenant ops (install runbook) | Ask the first customer for a reference call with a prospect |
| 12 | **≥₹40,000/month recurring or 1 migration paid** | Publish the measured accuracy card (only real numbers) | Decide: continue, narrow, or convert to a component sale |

**The one number to watch all quarter: replies per 20 messages.** It is upstream of everything and
it moves fastest when you change the first line.

---

# Three things to do today

1. **Run the tests and the sandbox once** (`cd Backend && /tmp/venv/bin/python -m pytest -q` and
   `uvicorn main:app` on `CIRA_DATA_SOURCE=simulator`) so that the first thing you show a partner
   is a working box, not a promise. The suite is green at 64 passing as of this document.
2. **Fill `ground_truth_sql` on ten questions and run the accuracy runner twice.** If the two runs
   agree, you have the beginning of the only asset in this plan that a competitor cannot copy
   quickly: measured accuracy on a named client's data.
3. **Send 20 first-touch messages** (§7.3) to the India list, and put Day 14 on a calendar.
   Everything else in this plan is downstream of that number.

# What I need to go deeper

| Need | Why | Unblocks |
|---|---|---|
| A real B1 sandbox (HANA **and** SQL Server) with Service Layer, or a partner who lends one for a day | The entire HANA/MSSQL/Service-Layer tier is unexercised; one day of a live system converts "works" from claim to fact | §1 rows for HANA, MSSQL, Service Layer, error handling |
| One partner's real messy sheet (with permission, anonymised) | The migration profiles are guesses about real-world headers until proven on one | §3 estimate → actual, and the accuracy suite's second scenario |
| Your target price list signed off by you (direct / white-label / unlimited) | §5 gives three shapes; only you can decide which one you will actually quote this month | §7 close scripts |
| Two hours with a CA on LUT, FIRC and GST on exports | The pricing plan assumes zero-rated exports with a LUT; that is a documentary process, not a decision | §5.3 and §9 |
| Decision-maker names for the ◻ rows in §4 | I will not invent them; the 20-minute method in §4.2 produces them at ~3 minutes per firm | §4.1 completeness, §7 sending |
