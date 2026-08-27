"""Admin panel: role gating, tenant validation, secret handling, login interplay.

The admin feature as first shipped had a hard-coded `admin` backdoor that ignored
every config knob, stored SAP passwords in plaintext, could be pointed at the
cloud metadata IP, and made /auth/login refuse ALL sign-ins until a row existed.
Each of those has a test here.
"""

import json

import pytest
from fastapi.testclient import TestClient

import config
import main
import tenants
from auth import create_token

ADMIN_PASSWORD = "test-admin-password-123"


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def admin_token(client):
    res = client.post("/auth/login", json={"employee_id": "admin", "password": ADMIN_PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _payload(**over):
    base = {
        "company_db": "ACME_PROD",
        "hana_address": "hana.acme.internal",
        "hana_port": 30015,
        "hana_user": "cira_ro",
        "hana_password": "env:ACME_HANA_PW",
    }
    base.update(over)
    return base


# ── the backdoor is gone ─────────────────────────────────────────────────────
def test_hardcoded_admin_login_endpoint_no_longer_exists(client):
    res = client.post("/admin/login", json={"username": "admin", "password": "***"})
    assert res.status_code in (404, 405)


def test_no_credential_literals_in_the_admin_path():
    source = (config.BASE_DIR / "admin_api.py").read_text(encoding="utf-8")
    assert "asdfghjkl" not in source
    assert 'password ==' not in source and "password ==" not in source
    main_source = (config.BASE_DIR / "main.py").read_text(encoding="utf-8")
    assert "admin_login" not in main_source


def test_all_admin_routes_require_the_admin_role(client, admin_token):
    employee = client.post(
        "/auth/login", json={"employee_id": "EMP-PLAIN", "password": "***"
    }
    )
    assert employee.status_code == 200
    plain = employee.json()["token"]

    assert client.get("/admin/connections").status_code in (401, 403)
    for method, path in (
        ("GET", "/admin/connections"),
        ("GET", "/admin/overview"),
        ("POST", "/admin/connections"),
        ("DELETE", "/admin/connections/1"),
    ):
        denied = client.request(method, path, json={}, headers=_hdr(plain))
        assert denied.status_code == 403, (method, path, denied.text)
        allowed = client.request(method, path, json=_payload(), headers=_hdr(admin_token))
        # admin gets past the role gate (422/409/404/2xx all prove authorisation passed)
        assert allowed.status_code != 403, (method, path, allowed.text)


def test_admin_role_cannot_be_forged_in_the_token(client):
    # An attacker who knows they need `roles: ["admin"]` still cannot mint it:
    # the payload is HMAC-signed with the server secret.
    token = create_token("EMP-X", "X", ["admin"])["token"]
    payload, _, signature = token.rpartition(".")
    tampered = f"{payload}.{signature[:-3]}aaa"
    assert client.get("/admin/connections", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


# ── validation ───────────────────────────────────────────────────────────────
def test_company_db_must_be_identifier_shaped(client, admin_token):
    for bad in ('ACME"; DROP', "has space", "", "x"):
        res = client.post("/admin/connections", json=_payload(company_db=bad), headers=_hdr(admin_token))
        assert res.status_code in (422, 400), bad


def test_hana_port_range_enforced(client, admin_token):
    for bad in (0, 70000):
        res = client.post("/admin/connections", json=_payload(hana_port=bad), headers=_hdr(admin_token))
        assert res.status_code == 422, bad


def test_metadata_and_loopback_targets_are_refused(client, admin_token):
    for host in ("169.254.169.254", "localhost", "127.0.0.1", "metadata.google.internal"):
        res = client.post("/admin/connections", json=_payload(hana_address=host), headers=_hdr(admin_token))
        assert res.status_code == 422, host
        assert "refuse" in res.json()["detail"].lower() or "refused" in res.json()["detail"].lower()


def test_validators_accept_legitimate_targets():
    assert tenants.valid_schema("acme_prod") == "ACME_PROD"
    assert tenants.valid_host("hana.acme.internal") == "hana.acme.internal"
    assert tenants.valid_host("10.20.30.40") == "10.20.30.40"
    assert tenants.valid_port("30015") == 30015
    tenants.assert_safe_target("10.20.30.40", 30015)   # private LAN is the normal case
    tenants.assert_safe_target("hana.acme.internal", 30013)
    with pytest.raises(ValueError):
        tenants.assert_safe_target("127.0.0.1", 30013)
    with pytest.raises(ValueError):
        tenants.valid_host("not a host!")


# ── secrets at rest ──────────────────────────────────────────────────────────
def test_unresolved_env_reference_is_visible_not_silent(client, admin_token):
    """env:VAR that is not set must be reported, not quietly disabled."""
    import os
    os.environ.pop("ACME_HANA_PW", None)
    created = client.post("/admin/connections", json=_payload(company_db="MISSINGREF"),
                          headers=_hdr(admin_token))
    assert created.status_code == 201
    assert created.json()["hana_secret_resolved"] is False
    import pytest as _pytest

    from sap.hana_backend import HanaBackend
    with _pytest.raises(Exception) as err:
        HanaBackend(host="h", user="u", password="", schema="S")
    assert "env:" in str(err.value) or "HANA_PASSWORD" in str(err.value)


def test_env_reference_is_stored_as_a_reference_only(client, admin_token, monkeypatch):
    monkeypatch.setenv("ACME_HANA_PW", "live-from-env")
    created = client.post("/admin/connections", json=_payload(), headers=_hdr(admin_token))
    assert created.status_code == 201, created.text
    body = created.json()
    listed = client.get("/admin/connections", headers=_hdr(admin_token)).json()["connections"]
    row = next(r for r in listed if r["company_db"] == "ACME_PROD")
    assert row["hana_secret_source"] == "env"
    for key in ("hana_password", "hana_secret", "sl_secret", "password"):
        assert key not in row
    assert "live-from-env" not in json.dumps(listed)
    # ... and the env value is what the tenant actually uses
    settings = config.tenant_for("ACME_PROD")
    assert settings["HANA_PASSWORD"] == "live-from-env"
    assert settings["HANA_HOST"] == "hana.acme.internal"
    assert settings["HANA_PORT"] == 30015


def test_plaintext_is_rejected_unless_explicitly_allowed(client, admin_token, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_PLAINTEXT_SECRETS", False, raising=False)
    res = client.post("/admin/connections", json=_payload(company_db="PLAINTESTDB",
                                                            hana_password="***"),
                      headers=_hdr(admin_token))
    # crypto available -> auto-encrypted; unavailable -> refused. Either way it
    # must never land on disk as the raw string.
    assert res.status_code in (201, 422)
    if res.status_code == 201:
        assert res.json()["hana_secret_source"] == "encrypted"
        listed = client.get("/admin/connections", headers=_hdr(admin_token)).json()["connections"]
        assert "raw-password" not in json.dumps(listed)
        row = next(r for r in listed if r["company_db"] == "PLAINTESTDB")
        assert row["hana_secret_source"] in ("encrypted", "plaintext")
    import credential_store

    # With crypto available a pasted password is auto-encrypted at rest…
    if credential_store.available():
        stored = credential_store.validate_for_storage("raw-password")
        assert stored.startswith("enc:") and credential_store.resolve(stored) == "raw-password"
    # …and plaintext only happens when the operator explicitly asks for it.
    monkeypatch.setattr(credential_store.config, "ALLOW_PLAINTEXT_SECRETS", True, raising=False)
    assert credential_store.validate_for_storage("raw-password") == "raw-password"
    monkeypatch.setattr(credential_store.config, "ALLOW_PLAINTEXT_SECRETS", False, raising=False)


def test_service_layer_credentials_are_separate_from_the_hana_user(client, admin_token):
    created = client.post(
        "/admin/connections",
        json=_payload(company_db="SLCORP", sl_user="manager", sl_password="env:SL_PW"),
        headers=_hdr(admin_token),
    )
    assert created.status_code == 201, created.text
    settings = config.tenant_for("SLCORP")
    assert settings["SAP_B1_USER"] == "manager"
    assert settings["SERVICE_LAYER_BASE"].endswith("/b1s/v1")
    # a Service Layer user without a secret is refused rather than half-configured
    bad = client.post("/admin/connections", json=_payload(company_db="SLBAD", sl_user="manager"),
                      headers=_hdr(admin_token))
    assert bad.status_code == 422


def test_duplicate_company_db_conflicts(client, admin_token):
    first = client.post("/admin/connections", json=_payload(company_db="DUPE"), headers=_hdr(admin_token))
    assert first.status_code == 201
    second = client.post("/admin/connections", json=_payload(company_db="DUPE"), headers=_hdr(admin_token))
    assert second.status_code == 409


def test_update_and_delete_round_trip(client, admin_token, monkeypatch):
    monkeypatch.setenv("ACME_HANA_PW", "x")
    created = client.post("/admin/connections", json=_payload(company_db="TEMPDB"), headers=_hdr(admin_token)).json()
    cid = created["id"]
    assert config.tenant_for("TEMPDB") is not None

    paused = client.put(f"/admin/connections/{cid}", json={"enabled": False}, headers=_hdr(admin_token))
    assert paused.status_code == 200 and paused.json()["enabled"] is False
    import asyncio

    asyncio.run(tenants.refresh(force=True))
    assert config.tenant_for("TEMPDB") is None, "a paused tenant must stop resolving"

    assert client.delete(f"/admin/connections/{cid}", headers=_hdr(admin_token)).status_code == 200
    asyncio.run(tenants.refresh(force=True))
    assert config.tenant_for("TEMPDB") is None
    assert client.delete(f"/admin/connections/{cid}", headers=_hdr(admin_token)).status_code == 404


# ── sign-in interplay (the bug that locked everybody out) ────────────────────
def test_sign_in_works_with_an_empty_registry(client):
    res = client.post("/auth/login", json={"employee_id": "EMP-OK", "password": "***"})
    assert res.status_code == 200, res.text


def test_sign_in_to_a_registered_tenant_and_reject_unknown(client, admin_token):
    client.post("/admin/connections", json=_payload(company_db="TENANT_A"), headers=_hdr(admin_token))
    ok = client.post("/auth/login", json={"employee_id": "EMP-A", "password": "***",
                                          "company_db": "TENANT_A"})
    assert ok.status_code == 200
    assert ok.json()["user"]["company_db"] == "TENANT_A"

    unknown = client.post("/auth/login", json={"employee_id": "EMP-A", "password": "***",
                                               "company_db": "NOT_REGISTERED_XYZ"})
    assert unknown.status_code == 403


def test_require_registered_company_db_refuses_the_default(client, admin_token, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_REGISTERED_COMPANY_DB", True, raising=False)
    res = client.post("/auth/login", json={"employee_id": "EMP-B", "password": "***"})
    assert res.status_code == 403
    assert "company" in res.json()["detail"].lower()


def test_overview_reports_per_tenant_sources(client, admin_token, monkeypatch):
    monkeypatch.setenv("ACME_HANA_PW", "x")
    client.post("/admin/connections", json=_payload(company_db="OVRDB"), headers=_hdr(admin_token))
    body = client.get("/admin/overview", headers=_hdr(admin_token)).json()
    assert "OVRDB" in body["company_dbs"]
    assert "hana" in body["per_tenant"]["OVRDB"]["sources"]
    assert body["policies"]["writes_enabled"] is False


def test_admin_actions_are_audited(client, admin_token, audit_lines):
    before = len(audit_lines())
    client.post("/admin/connections", json=_payload(company_db="AUDITDB"), headers=_hdr(admin_token))
    lines = audit_lines()[before:]
    created = [line for line in lines if line["action"] == "tenant_created"]
    assert created and created[-1]["company_db"] == "AUDITDB"
    assert "password" not in json.dumps(created).lower()


# ── defense in depth: identifiers reaching SQL text ─────────────────────────
def test_hana_identifiers_are_validated_before_reaching_sql():
    from sap.hana_backend import sql_ident
    from sap.types_ import SapUnavailableError

    assert sql_ident("ACME_PROD") == '"ACME_PROD"'
    for bad in ('ACME"."SYS', "A B", 'X" WHERE 1=1 --', ""):
        with pytest.raises(SapUnavailableError):
            sql_ident(bad)


def test_a_malicious_tenant_name_cannot_reach_the_database():
    """The admin panel value ends up in `schema`-position SQL; refuse it at the boundary."""
    with pytest.raises(ValueError):
        tenants.valid_schema('EVIL"."SYS')
