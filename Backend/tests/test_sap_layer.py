"""SQL guard, query builder and serialisation tests."""

import datetime as dt
import decimal

import pytest

from sap import query_spec, sql_guard
from sap.entities import decode_rows, encode_value, normalise_table_name
from sap.serialize import rows_to_jsonable, to_jsonable
from sap.types_ import ColumnInfo, SapDataError


# ── read-only guard ──────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM ORDR",
        "UPDATE OINV SET DocTotal = 0",
        "DROP TABLE OCRD",
        "SELECT 1; DROP TABLE OCRD",
        "CALL SOME_PROC()",
        "INSERT INTO OITM VALUES (1)",
        "  truncate table jdt1  ",
        "GRANT SELECT ON SCHEMA X TO Y",
    ],
)
def test_write_statements_are_rejected(statement):
    with pytest.raises(SapDataError):
        sql_guard.ensure_read_only(statement)


@pytest.mark.parametrize(
    "statement",
    [
        'SELECT * FROM ORDR',
        'WITH x AS (SELECT 1 AS a FROM ORDR) SELECT * FROM x',
        'SELECT REPLACE("CardName", \'a\', \'b\') FROM OCRD',
        "SELECT * FROM OINV WHERE Comments = 'do not delete this row'",
    ],
)
def test_select_statements_pass(statement):
    assert sql_guard.ensure_read_only(statement)


def test_row_limit_is_injected():
    sql = sql_guard.apply_row_limit("SELECT * FROM ORDR", 100, "hana")
    assert "LIMIT 100" in sql
    already = sql_guard.apply_row_limit("SELECT TOP 5 * FROM ORDR", 100, "hana")
    assert "LIMIT 100" not in already


def test_hana_to_sqlite_translation():
    out = sql_guard.translate_for_sqlite(
        'SELECT TOP 10 YEAR("DocDate") AS y FROM "CIRA"."ORDR"', "CIRA"
    )
    assert "strftime" in out
    assert "LIMIT 10" in out
    assert '"CIRA".' not in out


# ── value serialisation (the crash that killed every real HANA response) ─────
def test_decimal_date_and_bytes_are_json_safe():
    assert to_jsonable(decimal.Decimal("1450.00")) == 1450
    assert to_jsonable(decimal.Decimal("1450.55")) == 1450.55
    assert to_jsonable(dt.date(2024, 7, 2)) == "2024-07-02"
    assert to_jsonable(dt.datetime(2024, 7, 2, 0, 0, 0)) == "2024-07-02"
    assert to_jsonable(dt.datetime(2024, 7, 2, 13, 5, 9)) == "2024-07-02 13:05:09"
    assert to_jsonable(b"hello") == "hello"
    assert to_jsonable(memoryview(b"hi")) == "hi"
    assert to_jsonable(float("nan")) is None


def test_rows_to_jsonable_strips_char_padding():
    rows = rows_to_jsonable(["CardCode"], [("C20000   ",)])
    assert rows == [{"CardCode": "C20000"}]


# ── SAP semantics ────────────────────────────────────────────────────────────
def test_friendly_names_resolve_to_b1_tables():
    assert normalise_table_name("invoices") == "OINV"
    assert normalise_table_name("Sales Orders") == "ORDR"
    assert normalise_table_name("vendors") == "OCRD"
    assert normalise_table_name("journal lines") == "JDT1"
    assert normalise_table_name("OWOR") == "OWOR"


def test_status_words_are_encoded_to_b1_codes():
    assert encode_value("DocStatus", "Open") == "O"
    assert encode_value("DocStatus", "closed") == "C"
    assert encode_value("CardType", "vendor") == "S"
    assert encode_value("DocTotal", 100) == 100


def test_codes_are_decoded_for_humans():
    rows = decode_rows([{"DocStatus": "O", "CANCELED": "N", "CardType": "S"}])
    assert rows[0]["DocStatus"] == "Open"
    assert rows[0]["CANCELED"] == "Active"
    assert rows[0]["CardType"] == "Vendor"


# ── query builder ────────────────────────────────────────────────────────────
def _resolver():
    return query_spec.ColumnResolver(
        [
            ColumnInfo("DocNum", "INTEGER"),
            ColumnInfo("CardName", "NVARCHAR(100)", length=100),
            ColumnInfo("DocTotal", "DECIMAL(19,6)"),
            ColumnInfo("DocDate", "DATE"),
            ColumnInfo("DocStatus", "NVARCHAR(1)", length=1),
        ]
    )


def test_builder_parameterises_values():
    spec = query_spec.spec_from_payload(
        {
            "table": "ORDR",
            "filters": [{"column": "CardName", "op": "contains", "value": "'; DROP TABLE--"}],
            "limit": 10,
        }
    )
    sql, params = query_spec.build_select(spec, _resolver(), "hana", schema="CIRA")
    assert "DROP" not in sql
    assert params == ["%'; DROP TABLE--%"]
    assert 'SELECT TOP 10' in sql
    assert '"CIRA"."ORDR"' in sql


def test_unknown_column_is_rejected_with_suggestion():
    spec = query_spec.spec_from_payload(
        {"table": "ORDR", "filters": [{"column": "CardNam", "value": "x"}]}
    )
    with pytest.raises(SapDataError) as err:
        query_spec.build_select(spec, _resolver(), "hana")
    assert "CardName" in str(err.value)


def test_group_by_with_aggregate_and_year_filter():
    spec = query_spec.spec_from_payload(
        {
            "table": "ORDR",
            "group_by": ["CardName"],
            "aggregates": [{"func": "sum", "column": "DocTotal", "alias": "Total"}],
            "order_by": [{"column": "Total", "direction": "desc"}],
            "year": 2024,
        }
    )
    sql, params = query_spec.build_select(spec, _resolver(), "hana", schema="CIRA")
    assert 'GROUP BY "CardName"' in sql
    assert 'SUM("DocTotal") AS "Total"' in sql
    assert 'ORDER BY "Total" DESC' in sql
    assert 'YEAR("DocDate") = ?' in sql
    assert params == [2024]


def test_sqlite_dialect_uses_limit_and_strftime():
    spec = query_spec.spec_from_payload({"table": "ORDR", "year": 2024, "limit": 7})
    sql, params = query_spec.build_select(spec, _resolver(), "sqlite")
    assert "LIMIT 7" in sql
    assert "TOP" not in sql
    assert "strftime" in sql
