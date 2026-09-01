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


def _login(client, employee="admin", password="asdfghjkl;"):
    res = client.post("/auth/login", json={"employee_id": employee, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def test_health_is_public(client):
    assert client.get("/health").json()["status"] == "ok"


def test_login_rejects_bad_admin_password(client):
    res = client.post("/auth/login", json={"employee_id": "admin", "password": "nope"})
    assert res.status_code == 401


def test_endpoints_require_a_token(client):
    for path in ("/sessions", "/sap/health", "/sap/tables"):
        assert client.get(path).status_code in (401, 403)


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
