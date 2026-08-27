"""API-level tests: auth hardening, ownership checks and SSE streaming."""

import json

import pytest
from fastapi.testclient import TestClient

import main
from auth import create_token


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


import config  # noqa: E402

ADMIN_PASSWORD = "test-admin-password-123"  # set by conftest, never a shipped default


def _login(client, employee="admin", password=ADMIN_PASSWORD):
    res = client.post("/auth/login", json={"employee_id": employee, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def test_health_is_public(client):
    assert client.get("/health").json()["status"] == "ok"


def test_health_does_not_describe_the_topology(client):
    body = client.get("/health").json()
    blob = json.dumps(body).lower()
    for needle in ("host", "port", "system", "schema", "manager", "30013", "50000"):
        assert needle not in blob, f"/health leaked {needle!r}"


def test_login_rejects_bad_admin_password(client):
    res = client.post("/auth/login", json={"employee_id": "admin", "password": "nope"})
    assert res.status_code == 401


def test_endpoints_require_a_token(client):
    # /sap/health used to be public and returned host, port, schema, ERP user and
    # the Service Layer URL. A test asserting otherwise was failing on main.
    for path in ("/sessions", "/sap/health", "/sap/tables", "/auth/me"):
        assert client.get(path).status_code in (401, 403), path


def test_sap_health_never_contains_connection_strings(client):
    token = _login(client)
    body = client.get("/sap/health", headers={"Authorization": f"Bearer {token}"}).json()
    # config_warnings deliberately quote env-var NAMES, so scan the data-bearing
    # parts only: nothing there may carry a host, port, principal or URL.
    structure = json.dumps(
        {k: body[k] for k in ("probe", "attempts", "config") if k in body}
    ).lower()
    for needle in ("password", "host", "port", "base_url", "user",
                   str(config.HANA_HOST).lower(), str(config.SERVICE_LAYER_BASE).lower()):
        if not needle:
            continue
        assert needle not in structure, f"/sap/health exposes {needle!r}"
    assert body["config"]["hana"]["configured"] in (True, False)


def test_login_rejects_unknown_company_db(client):
    res = client.post(
        "/auth/login",
        json={"employee_id": "EMP-X", "password": "whatever", "company_db": "NOT_REGISTERED"},
    )
    assert res.status_code == 403


def test_forged_unsigned_token_is_rejected(client):
    # This is exactly what the old frontend minted client-side.
    import base64

    forged = base64.b64encode(json.dumps({"employee_id": "ADMIN-001"}).encode()).decode()
    res = client.get("/sessions", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == 401


def test_tampered_signature_is_rejected(client):
    token = _login(client)
    payload, _, signature = token.rpartition(".")
    tampered = f"{payload}.{signature[:-2]}xx"
    res = client.get("/sessions", headers={"Authorization": f"Bearer {tampered}"})
    assert res.status_code == 401


def test_expired_token_is_rejected(client):
    token = create_token("EMP-EXP", ttl=-10)["token"]
    res = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def _stream_chat(client, token, query, session_id):
    events = []
    with client.stream(
        "POST",
        "/chat",
        json={"query": query, "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
    ) as response:
        assert response.status_code == 200
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                raw, buffer = buffer.split("\n\n", 1)
                for line in raw.splitlines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))
    return events


def test_chat_streams_table_chart_and_summary(client):
    token = _login(client)
    events = _stream_chat(client, token, "Show me open invoices", "sess-chat-1")
    kinds = [e["type"] for e in events]
    assert "tabular" in kinds
    assert "chart" in kinds
    assert "chunk" in kinds
    assert kinds[-1] == "done"

    table = next(e for e in events if e["type"] == "tabular")
    assert len(table["data"]) > 0
    assert table["meta"]["source"]
    # every payload must be JSON serialisable (Decimals/dates used to explode here)
    json.dumps(events)


def test_history_is_persisted_with_rows_and_chart(client):
    token = _login(client)
    _stream_chat(client, token, "Top vendors by purchase order value", "sess-chat-2")
    res = client.get("/history/sess-chat-2", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    messages = res.json()["messages"]
    assert messages[0]["role"] == "user"
    assistant = messages[-1]
    assert assistant["role"] == "assistant"
    assert assistant["data"]
    assert assistant["chart"]


def test_other_employees_cannot_read_or_hijack_a_session(client):
    owner = _login(client)
    _stream_chat(client, owner, "Show me open invoices", "sess-private")

    intruder = _login(client, employee="EMP-INTRUDER", password="whatever")
    assert client.get("/history/sess-private", headers={"Authorization": f"Bearer {intruder}"}).status_code == 403

    events = _stream_chat(client, intruder, "Show me open invoices", "sess-private")
    assert any(e["type"] == "error" for e in events)

    # ... and the owner's history is untouched
    messages = client.get("/history/sess-private", headers={"Authorization": f"Bearer {owner}"}).json()["messages"]
    assert all(m["role"] in ("user", "assistant") for m in messages)


def test_sessions_are_scoped_per_employee(client):
    token_a = _login(client, employee="EMP-A", password="x")
    _stream_chat(client, token_a, "Show me open invoices", "sess-emp-a")
    token_b = _login(client, employee="EMP-B", password="x")

    listing_b = client.get("/sessions", headers={"Authorization": f"Bearer {token_b}"}).json()["sessions"]
    assert all(s["id"] != "sess-emp-a" for s in listing_b)

    listing_a = client.get("/sessions", headers={"Authorization": f"Bearer {token_a}"}).json()["sessions"]
    assert any(s["id"] == "sess-emp-a" for s in listing_a)


def test_rename_and_delete_session(client):
    token = _login(client, employee="EMP-C", password="x")
    _stream_chat(client, token, "Show me open invoices", "sess-emp-c")
    headers = {"Authorization": f"Bearer {token}"}

    assert client.put("/session/sess-emp-c", json={"title": "Q3 review"}, headers=headers).status_code == 200
    titles = [s["title"] for s in client.get("/sessions", headers=headers).json()["sessions"]]
    assert "Q3 review" in titles

    assert client.delete("/session/sess-emp-c", headers=headers).status_code == 200
    assert client.get("/history/sess-emp-c", headers=headers).status_code == 403


def test_sap_diagnostics_endpoints(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    health = client.get("/sap/health", headers=headers).json()
    assert health["tables_visible"] > 10

    tables = client.get("/sap/tables", params={"pattern": "OIN"}, headers=headers).json()
    assert any(t["table"].startswith("OIN") for t in tables["tables"])

    detail = client.get("/sap/table/OINV", headers=headers).json()
    assert detail["table"] == "OINV"
    assert detail["columns"]


# ── writes: opt-in, role-gated, entity-allowlisted, audited ─────────────────
def test_sap_write_is_disabled_by_default(client):
    token = _login(client)
    res = client.post(
        "/sap/write",
        json={"entity": "BusinessPartners", "data": {"CardCode": "X"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert "disabled" in res.json()["detail"].lower()


def test_sap_write_requires_an_admin_role(client, monkeypatch):
    monkeypatch.setattr(config, "SAP_WRITE_ENABLED", True, raising=False)
    employee = _login(client, employee="EMP-PLAIN", password="x")
    res = client.post(
        "/sap/write",
        json={"entity": "BusinessPartners", "data": {"CardCode": "X"}},
        headers={"Authorization": f"Bearer {employee}"},
    )
    assert res.status_code == 403
    assert "role" in res.json()["detail"].lower()


def test_sap_write_blocks_entities_outside_the_allowlist(client, monkeypatch):
    monkeypatch.setattr(config, "SAP_WRITE_ENABLED", True, raising=False)
    token = _login(client)
    for entity in ("Users", "ServiceLayers", "CompanyDetails"):
        res = client.post(
            "/sap/write",
            json={"entity": entity, "data": {"x": 1}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403, entity
        assert "allowlist" in res.json()["detail"]


def test_sap_write_never_writes_from_the_sandbox(client, monkeypatch):
    """Even an admin must not get a fake 'success' while on simulated data."""
    monkeypatch.setattr(config, "SAP_WRITE_ENABLED", True, raising=False)
    token = _login(client)
    res = client.post(
        "/sap/write",
        json={"entity": "BusinessPartners", "table": "OCRD",
              "data": {"CardCode": "C999", "CardName": "Nobody", "CardType": "C"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422
    detail = res.json()["detail"].lower()
    assert "sandbox" in detail or "service layer" in detail


def test_write_attempts_and_failures_are_audited(client, monkeypatch, audit_lines):
    monkeypatch.setattr(config, "SAP_WRITE_ENABLED", True, raising=False)
    # Demo mode is on for the suite, so a wrong password only fails once it is off.
    monkeypatch.setattr(config, "ALLOW_ANY_EMPLOYEE", False, raising=False)
    before = len(audit_lines())
    token = _login(client)
    client.post("/sap/write", json={"entity": "BusinessPartners", "data": {"CardCode": "Z"}},
                headers={"Authorization": f"Bearer {token}"})
    denied = client.post("/auth/login", json={"employee_id": "ghost", "password": "nope"})
    assert denied.status_code == 401
    lines = audit_lines()[before:]
    actions = {line["action"] for line in lines}
    assert "login" in actions
    assert "sap_write_attempt" in actions
    failure = next(line for line in lines if line["action"] == "login_failed")
    assert failure["employee_id"] == "ghost"
    # ... and the audit trail never stores the password it was handed
    assert "nope" not in json.dumps(lines)


def test_queries_against_the_erp_are_audited(client, audit_lines):
    token = _login(client)
    before = len(audit_lines())
    _stream_chat(client, token, "Show me open invoices", "sess-audit-sql")
    actions = {line["action"] for line in audit_lines()[before:]}
    assert "sap_query" in actions or "sap_sql" in actions


def test_upload_rejects_oversize_before_buffering_it(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 64, raising=False)
    token = _login(client)
    res = client.post(
        "/upload",
        files={"file": ("big.csv", b"x" * 5000, "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 413


def test_upload_refuses_binaries(client):
    token = _login(client)
    res = client.post(
        "/upload",
        files={"file": ("payload.exe", b"MZ" + bytes(4) + b"bin", "application/octet-stream")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 415


def test_transcribe_is_closed_without_a_provider_key(client, monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "", raising=False)
    token = _login(client)
    res = client.post(
        "/transcribe",
        files={"file": ("a.webm", b"audio-bytes", "audio/webm")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 503


def test_transcribe_rejects_non_audio(client, monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key", raising=False)
    token = _login(client)
    res = client.post(
        "/transcribe",
        files={"file": ("evil.html", b"<script>", "text/html")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


def test_history_exposes_every_table_from_one_answer(client):
    """A multi-part answer used to persist only its last table."""
    token = _login(client)
    _stream_chat(client, token, "Show me open invoices and then the sales orders", "sess-multi")
    messages = client.get("/history/sess-multi", headers={"Authorization": f"Bearer {token}"}).json()["messages"]
    assistant = messages[-1]
    assert assistant["data"] is not None
    assert isinstance(assistant["tables"], list)


def test_upload_returns_text_context(client):
    token = _login(client)
    res = client.post(
        "/upload",
        files={"file": ("notes.csv", b"item,qty\nA1,5\n", "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["usable_as_context"] is True
    assert "item,qty" in body["text_preview"]
