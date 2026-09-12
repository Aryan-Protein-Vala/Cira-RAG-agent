"""Excel → SAP B1 migration tests.

These cover the defects that made the old /admin/migration endpoints unusable:
CSV that was handed to openpyxl, types destroyed by str(), a push that counted a
skipped row as a success, and a module that could not be imported at all.

Everything runs against the offline sandbox: no ERP, no network.
"""

import io
import json

import openpyxl
import pytest
from fastapi.testclient import TestClient

import main
from auth import create_token

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def _admin_token() -> str:
    minted = create_token("ADMIN-001", "Test Admin", ["partner_admin", "superadmin"],
                          company_db="CIRA_TEST")
    return minted["token"]


def _auth() -> dict:
    return {"Authorization": f"Bearer {_admin_token()}"}


def _xlsx(rows) -> bytes:
    wb = openpyxl.Workbook()
    sheet = wb.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ── parsing ─────────────────────────────────────────────────────────────────
def test_csv_is_actually_parsed(client):
    """A .csv used to pass the extension check and then fail in openpyxl."""
    csv_bytes = (
        "Customer Code,Customer Name,Type,Email\n"
        "C9001,Acme Traders,customer,ap@acme.example.com\n"
        "C9002,Zenith Supplies,customer,ap@zenith.example.com\n"
    ).encode()
    res = client.post(
        "/admin/migration/upload",
        files={"file": ("partners.csv", csv_bytes, "text/csv")},
        data={"target": "BusinessPartners"},
        headers=_auth(),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_rows"] == 2
    targets = {h["target"] for h in body["headers"] if h["target"]}
    assert {"CardCode", "CardName", "CardType", "E_Mail"} <= targets


def test_xlsx_values_keep_their_type(client):
    """Numbers and dates must not be flattened to strings."""
    payload = _xlsx([
        ["ItemCode", "ItemName", "Item Group", "Average Price"],
        ["A9001", "Test Widget", 100, 1250.5],
        ["A9002", "Second Widget", 100, 999],
    ])
    res = client.post(
        "/admin/migration/upload",
        files={"file": ("items.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"target": "Items"},
        headers=_auth(),
    )
    assert res.status_code == 200, res.text
    first = res.json()["raw_data"][0]
    assert first[0] == "A9001"
    assert first[2] == 100          # int, not "100"
    assert first[3] == 1250.5       # float preserved


def test_unsupported_file_type_is_rejected(client):
    res = client.post(
        "/admin/migration/upload",
        files={"file": ("data.pdf", b"%PDF-1.4", "application/pdf")},
        headers=_auth(),
    )
    assert res.status_code == 400


def test_targets_not_yet_implemented_say_so(client):
    """Opening stock / A-R open items must refuse rather than half-import."""
    res = client.post(
        "/admin/migration/upload",
        files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")},
        data={"target": "OpeningStock"},
        headers=_auth(),
    )
    assert res.status_code == 501
    assert "Inventory Opening Balance" in res.json()["detail"]


# ── validation ──────────────────────────────────────────────────────────────
def _upload_and_validate(client, rows, target="BusinessPartners"):
    res = client.post(
        "/admin/migration/upload",
        files={"file": ("p.csv", rows.encode(), "text/csv")},
        data={"target": target},
        headers=_auth(),
    )
    assert res.status_code == 200, res.text
    upload = res.json()
    validate = client.post(
        "/admin/migration/validate",
        json={"target": target, "mapping": upload["headers"], "rows": upload["raw_data"]},
        headers=_auth(),
    )
    assert validate.status_code == 200, validate.text
    return upload, validate.json()


def test_validation_reports_the_failing_row_and_reason(client):
    csv_text = (
        "CardCode,CardName,Type,GSTIN\n"
        "C9001,Good Customer,customer,27ABCDE1234F1Z5\n"
        "C9002,,customer,27ABCDE1234F1Z5\n"          # CardName missing
        "C9002,Duplicate Code,customer,27ABCDE1234F1Z5\n"  # duplicate key
        "C9003,Short GST,customer,GST123\n"          # 6 chars, not 15
    )
    _, report = _upload_and_validate(client, csv_text)
    assert report["valid_count"] == 1
    assert report["error_count"] == 3
    # Failures carry the file line number, not just a count.
    assert report["failed_row_numbers"] == [2, 3, 4]
    reasons = json.dumps(report["errors"])
    assert "CardName is required" in reasons
    assert "duplicate" in reasons.lower()
    assert "15" in reasons


def test_column_report_shows_coverage(client):
    csv_text = (
        "CardCode,CardName,Type,Email\n"
        "C9001,Acme,customer,ap@acme.example.com\n"
        "C9002,Zenith,customer,\n"
    )
    _, report = _upload_and_validate(client, csv_text)
    coverage = {c["field"]: c for c in report["column_report"]}
    assert coverage["E_Mail"]["filled"] == 1
    assert coverage["E_Mail"]["blank"] == 1


def test_header_found_below_title_rows(client):
    csv_text = (
        "Customer Master Upload,,,,,\n"
        "Generated 2026-01-01,,,,,\n"
        "CardCode,CardName,Type,GSTIN,City,Phone\n"
        "C9001,Acme Traders,customer,27ABCDE1234F1Z5,Mumbai,9820011223\n"
    )
    upload, report = _upload_and_validate(client, csv_text)
    assert upload["header_row"] == 3
    assert report["valid_count"] == 1


# ── push ────────────────────────────────────────────────────────────────────
def test_push_creates_then_updates_and_counts_agree(client):
    """The core regression: a re-push must correct the row, not count a skip."""
    csv_text = (
        "CardCode,CardName,Type,City\n"
        "C9101,Push Test One,customer,Mumbai\n"
        "C9102,Push Test Two,customer,Pune\n"
    )
    _, report = _upload_and_validate(client, csv_text)
    assert report["valid_count"] == 2

    first = client.post("/admin/migration/push",
                        json={"target": "BusinessPartners", "valid_rows": report["valid_rows"]},
                        headers=_auth())
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["created"] == 2
    assert body["failed"] == 0
    assert body["success"] == body["created"] + body["updated"] + body["unchanged"]

    # Byte-identical retry (the client's response was lost): the idempotency key
    # is content-derived, so this replays the stored result instead of pushing
    # a second time.
    retry = client.post("/admin/migration/push",
                        json={"target": "BusinessPartners", "valid_rows": report["valid_rows"]},
                        headers=_auth())
    assert retry.status_code == 200, retry.text
    assert retry.json()["idempotent_replay"] is True
    assert retry.json()["created"] == 2

    # A different batch re-sends the same two rows plus one new row. The two
    # existing rows must be reported as "unchanged" - not skipped, not created
    # again - and only the new row is a create.
    batch = report["valid_rows"] + [{"CardCode": "C9103", "CardName": "Push Test Three",
                                     "CardType": "C", "City": "Delhi"}]
    third = client.post("/admin/migration/push",
                        json={"target": "BusinessPartners", "valid_rows": batch},
                        headers=_auth())
    assert third.status_code == 200, third.text
    result = third.json()
    assert result["created"] == 1
    assert result["unchanged"] == 2
    assert result["updated"] == 0
    assert result["success"] == 3

    # Corrected data → an update. CardType is unchanged ("C"); reads decode it to
    # "Customer" for humans, so the diff must re-encode before comparing or every
    # re-push would report a phantom change on every coded column.
    corrected = [{"CardCode": "C9101", "CardName": "Push Test One (renamed)",
                  "CardType": "C"}]
    fourth = client.post("/admin/migration/push",
                         json={"target": "BusinessPartners", "valid_rows": corrected},
                         headers=_auth())
    assert fourth.status_code == 200, fourth.text
    update = fourth.json()
    assert update["updated"] == 1
    assert update["results"][0]["changed_fields"] == ["CardName"]


def test_failed_rows_are_returned_for_a_targeted_re_push(client):
    """A row SAP rejects must come back by row number so it can be fixed alone."""
    # The second row is invalid. Push re-validates server-side, so it comes back
    # in failed_rows even though a client could have skipped /validate.
    rows = [{"CardCode": "C9201", "CardName": "Fine", "CardType": "C"},
            {"CardCode": "!!bad!!", "CardName": "Bad key", "CardType": "C"}]
    res = client.post("/admin/migration/push",
                      json={"target": "BusinessPartners", "valid_rows": rows},
                      headers=_auth())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["failed"] == 1
    assert body["errors"][0]["row"] == 2
    assert len(body["failed_rows"]) == 1
    assert body["failed_rows"][0]["CardCode"] == "!!bad!!"


def test_idempotency_key_makes_a_retry_a_no_op(client):
    rows = [{"CardCode": "C9301", "CardName": "Idem Test", "CardType": "C"}]
    key = "test-idempotency-key-0001"
    first = client.post("/admin/migration/push",
                        json={"target": "BusinessPartners", "valid_rows": rows},
                        headers={**_auth(), "Idempotency-Key": key})
    assert first.status_code == 200
    assert first.json()["created"] == 1

    # Simulate the client retrying because the response was lost.
    retry_rows = [{"CardCode": "C9302", "CardName": "Idem Test Retry", "CardType": "C"}]
    retry = client.post("/admin/migration/push",
                        json={"target": "BusinessPartners", "valid_rows": retry_rows},
                        headers={**_auth(), "Idempotency-Key": key})
    assert retry.status_code == 200
    assert retry.json()["idempotent_replay"] is True
    assert retry.json()["created"] == 1  # the first result, not a new create


def test_capabilities_endpoint_is_readable(client):
    res = client.get("/admin/migration/capabilities", headers=_auth())
    assert res.status_code == 200
    body = res.json()
    assert {t["target"] for t in body["supported"]} == {"BusinessPartners", "Items"}
    assert "OpeningStock" in body["not_implemented"]


# ── dialect row caps (they must not emit LIMIT on SQL Server) ────────────────
def test_row_cap_uses_top_on_sql_server_and_limit_on_hana():
    from sap.sql_guard import apply_row_limit

    mssql = apply_row_limit("SELECT CardCode FROM OCRD", 100, "mssql")
    assert "TOP 100" in mssql and "LIMIT" not in mssql

    hana = apply_row_limit("SELECT CardCode FROM OCRD", 100, "hana")
    assert hana.rstrip().endswith("LIMIT 100")

    # An author-supplied cap is never stacked.
    assert apply_row_limit("SELECT TOP 5 CardCode FROM OCRD", 100, "mssql").count("TOP") == 1
