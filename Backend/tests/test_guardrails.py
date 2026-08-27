"""Guardrails: SQL scoping, dialect-correct row limits, param binding, OData safety.

Each test here corresponds to a hole in the previous build:
* the read-only guard let `SELECT * FROM "SYS"."USERS"` through (SYSTEM user!)
* `apply_row_limit` emitted `LIMIT` for SQL Server, i.e. invalid T-SQL
* `mssql.execute` did `sql.replace("?", "%s")`, corrupting literal `?` in data
* the Service Layer path took column names unvalidated into `$filter`
"""

import pytest

from sap import sql_guard
from sap.query_spec import ColumnResolver, build_select, spec_from_payload
from sap.service_layer import _odata_clause, map_field, safe_odata_name
from sap.types_ import ColumnInfo, SapDataError


# ── scoping ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "statement",
    [
        'SELECT "user_name", "password" FROM "SYS"."USERS"',
        "SELECT * FROM SYS.CONFIGURATION",
        'SELECT * FROM "SYS"."LICENSE"',
        'SELECT * FROM "OTHER_SCHEMA"."OINV"',
        "SELECT * FROM sys.sql_logins",
        'SELECT * FROM "ACME"."OINV" JOIN "SYS"."DB_USERS" ON 1=1',
    ],
)
def test_reads_outside_the_company_schema_are_denied(statement):
    with pytest.raises(SapDataError):
        sql_guard.enforce_scope(statement, ["ACME"])


@pytest.mark.parametrize(
    "statement",
    [
        'SELECT * FROM "ACME"."OINV"',
        "SELECT * FROM OINV",
        'SELECT * FROM "SYS"."TABLE_COLUMNS" WHERE SCHEMA_NAME = \'ACME\'',
        'SELECT * FROM "ACME_PROD"."OITM"',
        "SELECT a.\"DocNum\" FROM ORDR a",
    ],
)
def test_in_scope_reads_are_allowed(statement):
    assert sql_guard.enforce_scope(statement, ["ACME", "ACME_PROD"])


def test_extra_schemas_can_be_granted_explicitly():
    with pytest.raises(SapDataError):
        sql_guard.enforce_scope("SELECT * FROM REPORTING.V_WS_SALES", ["ACME"])
    assert sql_guard.enforce_scope("SELECT * FROM REPORTING.V_WS_SALES", ["ACME", "REPORTING"])


def test_locking_clauses_are_rejected():
    with pytest.raises(SapDataError):
        sql_guard.ensure_read_only("SELECT * FROM ORDR FOR UPDATE")


def test_identifiers_containing_risky_words_are_not_false_positives():
    # B1 user tables/fields love words like SET/EXPORT; the tokenizer keeps the
    # underscores together so these must stay queryable.
    sql = 'SELECT "U_SET_FLAG", "U_EXPORT_REF" FROM "@MY_UDT" WHERE "U_PROCEDURE_ID" > 0'
    assert sql_guard.ensure_read_only(sql)


# ── dialects ─────────────────────────────────────────────────────────────────
def test_mssql_row_limit_uses_offset_fetch_not_limit():
    capped = sql_guard.apply_row_limit('SELECT "DocNum" FROM [OINV]', 500, "mssql")
    assert "LIMIT" not in capped
    assert "FETCH NEXT 500 ROWS ONLY" in capped
    assert "ORDER BY" in capped  # T-SQL requires it before OFFSET


def test_mssql_row_limit_appends_to_an_existing_order_by():
    sql = 'SELECT "CardName" FROM [OCRD] ORDER BY "Balance" DESC'
    capped = sql_guard.apply_row_limit(sql, 50, "mssql")
    assert "OFFSET 0 ROWS" in capped
    # must not invent a second ORDER BY
    assert capped.upper().count("ORDER BY") == 1


def test_hana_row_limit_is_a_wrap():
    assert "LIMIT 25" in sql_guard.apply_row_limit("SELECT 1 FROM ORDR", 25, "hana")


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT TOP 10 \"DocNum\" FROM ORDR",
        "SELECT DISTINCT TOP 10 \"DocNum\" FROM ORDR",
        "SELECT * FROM ORDR LIMIT 10",
        "SELECT * FROM ORDR ORDER BY 1 OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY",
    ],
)
def test_existing_row_limits_are_respected(statement):
    assert sql_guard.has_row_limit(statement)
    assert sql_guard.apply_row_limit(statement, 500, "hana") == statement


# ── paramstyle ───────────────────────────────────────────────────────────────
def test_rebind_skips_question_marks_inside_literals():
    sql = "SELECT a FROM t WHERE b = ? AND c LIKE '%?%'"
    # the `?` in the literal is data; the driver still needs its `%` doubled
    assert sql_guard.rebind_param_markers(sql, "format") == (
        "SELECT a FROM t WHERE b = %s AND c LIKE '%%?%%'"
    )


def test_rebind_escapes_stray_percent_for_mssql():
    sql = "SELECT a FROM t WHERE c LIKE '%foo%' AND d = ?"
    out = sql_guard.rebind_param_markers(sql, "format")
    assert "LIKE '%%foo%%'" in out and "= %s" in out
    assert out.count("%s") == 1  # exactly one marker, never an accidental one


def test_qmark_dialect_is_unchanged():
    sql = "SELECT a FROM t WHERE b = ? AND c LIKE '%?%'"
    assert sql_guard.rebind_param_markers(sql, "qmark") == sql


# ── query builder dialects ────────────────────────────────────────────────────
def _resolver():
    return ColumnResolver(
        [
            ColumnInfo("DocNum", "INTEGER"),
            ColumnInfo("CardName", "NVARCHAR(100)", length=100),
            ColumnInfo("DocTotal", "DECIMAL(19,6)"),
            ColumnInfo("DocDate", "DATE"),
        ]
    )


def test_mssql_identifiers_use_brackets_and_dbo():
    spec = spec_from_payload({"table": "OINV", "columns": ["DocNum", "CardName"], "limit": 5})
    sql, _ = build_select(spec, _resolver(), "mssql", schema="dbo")
    assert "[dbo].[OINV]" in sql
    assert '"OINV"' not in sql
    assert "[CardName]" in sql


def test_mssql_uses_ltrim_rtrim_for_padded_codes():
    spec = spec_from_payload(
        {"table": "OINV", "filters": [{"column": "CardName", "value": "ACME"}]}
    )
    sql, params = build_select(spec, _resolver(), "mssql", schema="dbo")
    assert "LTRIM(RTRIM([CardName]))" in sql
    assert "UPPER(TRIM(" not in sql  # TRIM() would break on SQL Server < 2017
    assert params == ["ACME"]


def test_hana_keeps_double_quotes():
    spec = spec_from_payload({"table": "OINV", "columns": ["DocNum"]})
    sql, _ = build_select(spec, _resolver(), "hana", schema="ACME")
    assert '"ACME"."OINV"' in sql and '"DocNum"' in sql


# ── Service Layer identifier validation ─────────────────────────────────────
@pytest.mark.parametrize(
    "bad",
    [
        "CardCode' eq 'x' or '1' eq '1",
        "DocumentStatus eq 'bost_Open' or 1 eq 1",
        "$filter=x",
        "CardName; DROP TABLE ORDR",
        "",
        "2bad",
    ],
)
def test_odata_field_names_are_validated(bad):
    with pytest.raises(SapDataError):
        safe_odata_name(bad)


def test_odata_clause_rejects_injection_before_building_the_filter():
    with pytest.raises(SapDataError):
        _odata_clause("CardCode' eq 'a' or '1' eq '1", "eq", "C001")


def test_odata_values_are_still_escaped():
    clause = _odata_clause("CardName", "eq", "O'Brien")
    assert clause == "CardName eq 'O''Brien'"


def test_map_field_validates_both_directions():
    assert map_field("OCRD", "CardName") == "CardName"
    assert map_field("OITM", "OnHand") == "QuantityOnStock"
    with pytest.raises(SapDataError):
        map_field("OCRD", "anything' or '1' eq '1")


# ── the Service Layer retry must not silently drop the query ────────────────
def test_service_layer_retry_keeps_filter_and_top(monkeypatch):
    import threading

    from sap.service_layer import ServiceLayerBackend

    sl = object.__new__(ServiceLayerBackend)
    sl.base = "https://sl.internal/b1s/v1"
    sl.company = "ACME"
    sl.user = "manager"
    sl.password = "x"
    sl.schema = "ACME"
    sl._cookies = {"B1SESSION": "s"}
    sl._expires_at = 0.0
    sl._lock = threading.Lock()
    sl._entity_sets = None
    sl._ping_cache = None

    seen = []

    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.text = ""

        def json(self):
            return {"value": []}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            seen.append(params)
            return _Resp(401 if len(seen) == 1 else 200)

    monkeypatch.setattr(sl, "_client", lambda cookies=None: _Client())
    monkeypatch.setattr(sl, "_login", lambda force=False: {"B1SESSION": "s"})

    sl._get("Orders", {"$top": 5, "$filter": "DocStatus eq 'bost_Open'"})

    assert len(seen) == 2, "the request should have been retried once"
    assert seen[0] == seen[1], "a re-authenticated retry must repeat $filter/$top"
