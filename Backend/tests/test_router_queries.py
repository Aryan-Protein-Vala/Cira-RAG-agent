"""End-to-end data-layer tests against the offline SAP B1 sandbox."""

import pytest

from sap import router as sap
from sap.charts import build_chart
from sap.types_ import SapDataError

pytestmark = pytest.mark.asyncio


async def test_backend_is_reachable_and_has_tables():
    info = await sap.health()
    assert info["active_backend"]
    assert info["tables_visible"] > 10


async def test_describe_known_and_friendly_tables():
    described = await sap.describe_table("invoices")
    assert described["table"] == "OINV"
    assert any(c["column"] == "DocTotal" for c in described["columns"])
    assert described["row_count"] > 0


async def test_unknown_table_raises_instead_of_silently_returning_orders():
    # The old client mapped every unknown entity to ORDR and returned sales
    # orders as if they were the requested data.
    with pytest.raises(SapDataError):
        await sap.run_query({"table": "NOT_A_REAL_TABLE"})


async def test_status_filter_uses_b1_codes():
    result = await sap.run_query(
        {"table": "invoices", "filters": [{"column": "DocStatus", "value": "Open"}], "limit": 25}
    )
    assert result.ok
    assert result.row_count > 0
    assert all(row["DocStatus"] == "Open" for row in result.rows)
    assert result.total_available is None or result.total_available >= result.row_count


async def test_year_filter_is_applied():
    result = await sap.run_query({"table": "orders", "year": 2024, "limit": 50})
    assert all(str(row["DocDate"]).startswith("2024") for row in result.rows)


async def test_group_by_aggregate_returns_totals():
    result = await sap.run_query(
        {
            "table": "purchase orders",
            "group_by": ["CardName"],
            "aggregates": [{"func": "sum", "column": "DocTotal", "alias": "Total"}],
            "order_by": [{"column": "Total", "direction": "desc"}],
            "limit": 5,
        }
    )
    assert result.row_count == 5
    totals = [row["Total"] for row in result.rows]
    assert totals == sorted(totals, reverse=True)


async def test_free_text_search():
    result = await sap.run_query({"table": "business partners", "search": "Acme", "limit": 10})
    assert result.row_count > 0
    assert any("acme" in str(row).lower() for row in result.rows)


async def test_raw_sql_join_across_header_and_lines():
    result = await sap.run_sql(
        'SELECT T1."CardName", SUM(T0."LineTotal") AS "Revenue" '
        'FROM RDR1 T0 JOIN ORDR T1 ON T0."DocEntry" = T1."DocEntry" '
        'GROUP BY T1."CardName" ORDER BY "Revenue" DESC',
        limit=5,
    )
    assert result.ok
    assert result.row_count == 5
    assert "Revenue" in result.columns


async def test_raw_sql_write_is_blocked():
    with pytest.raises(SapDataError):
        await sap.run_sql("DELETE FROM ORDR")


async def test_schema_search_finds_columns_anywhere():
    found = await sap.search_schema("warehouse")
    tables = {t["table"] for t in found["tables"]}
    suggestions = {s["table"] for s in found["suggested_entities"]}
    assert "OWHS" in tables or "OWHS" in suggestions
    assert found["columns"] or suggestions


async def test_row_cap_is_enforced():
    result = await sap.run_query({"table": "orders", "limit": 10_000_000})
    assert result.row_count <= 10_000  # CIRA_MAX_ROW_LIMIT


async def test_chart_aggregates_instead_of_plotting_every_row():
    result = await sap.run_query({"table": "orders", "limit": 400})
    chart = build_chart(result.rows, "ORDR", user_query="show me orders", entity_label="ORDR")
    assert chart is not None
    assert 2 <= len(chart["data"]) <= 21
    assert chart["xKey"] in result.columns
    keys = set(chart["data"][0].keys())
    assert chart["yKey"] in keys


async def test_chart_type_follows_the_question():
    result = await sap.run_query({"table": "items", "limit": 200})
    pie = build_chart(result.rows, "OITM", user_query="give me a pie chart of inventory")
    assert pie["chartType"] == "pie"
    trend = build_chart(
        (await sap.run_query({"table": "invoices", "limit": 300})).rows,
        "OINV",
        user_query="monthly revenue trend",
    )
    assert trend["chartType"] in ("line", "area")
