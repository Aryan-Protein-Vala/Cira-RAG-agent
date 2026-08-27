"""Configuration policy: nothing secret in source, HANA first, no unsafe defaults.

These tests exist because the shipped defaults were the actual incident:
`MSSQL_PASSWORD` had a real `sa` password as its *default*, which (a) leaked a
production credential into git and (b) made the "auto" selector prefer SQL
Server over the intended HANA connection — a reporting tool quietly answering
from the wrong company database.
"""

import re
from pathlib import Path

import pytest

import config

CONFIG_SOURCE = (Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8")
ENV_EXAMPLE = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "setting",
    [
        "HANA_PASSWORD", "HANA_USER", "HANA_HOST", "HANA_SCHEMA",
        "MSSQL_PASSWORD", "MSSQL_USER", "MSSQL_HOST", "MSSQL_DATABASE",
        "SAP_B1_PASSWORD", "SAP_B1_USER", "SAP_B1_HOST",
        "CIRA_ADMIN_ID", "CIRA_ADMIN_PASSWORD", "CIRA_SECRET_KEY",
    ],
)
def test_no_credential_or_topology_default_in_source(setting):
    """`_str("X", "value")` with a non-empty default is how the leak happened."""
    pattern = re.compile(rf'_str\(\s*"{re.escape(setting)}"\s*,\s*"[^"]+"')
    assert not pattern.search(CONFIG_SOURCE), f"{setting} must default to empty, not a literal"


def test_no_private_hostnames_in_the_example_env():
    for line in ENV_EXAMPLE.splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        value = line.split("=", 1)[1].strip()
        assert not re.search(r"\b(\d{1,3}\.){3}\d{1,3}\b", value), f"IP in .env.example: {line}"
        assert "LIVE" not in value.upper() or value == "", f"suspicious DB name in .env.example: {line}"


def test_hana_is_the_default_preference_order():
    assert config.DATA_SOURCE_ORDER[0] == "hana"
    assert config.DATA_SOURCE_ORDER.index("hana") < config.DATA_SOURCE_ORDER.index("mssql")


def test_auto_only_offers_fully_configured_sources(monkeypatch):
    monkeypatch.setattr(config, "DATA_SOURCE", "auto")
    monkeypatch.setattr(config, "SIMULATOR_ALLOWED", False)
    for key in ("HANA_HOST", "HANA_USER", "HANA_PASSWORD", "HANA_SCHEMA",
                "MSSQL_HOST", "MSSQL_USER", "MSSQL_PASSWORD", "MSSQL_DATABASE",
                "SAP_B1_HOST", "SAP_B1_USER", "SAP_B1_PASSWORD"):
        monkeypatch.setattr(config, key, "", raising=False)
    assert config.enabled_sources() == []


def test_enabled_sources_follow_configuration_and_order(monkeypatch):
    monkeypatch.setattr(config, "SIMULATOR_ALLOWED", True)
    monkeypatch.setattr(config, "HANA_HOST", "hana.internal")
    monkeypatch.setattr(config, "HANA_USER", "cira_ro")
    monkeypatch.setattr(config, "HANA_PASSWORD", "x")
    monkeypatch.setattr(config, "HANA_SCHEMA", "ACME_PROD")
    monkeypatch.setattr(config, "MSSQL_HOST", "legacy.internal")
    monkeypatch.setattr(config, "MSSQL_USER", "cira_ro")
    monkeypatch.setattr(config, "MSSQL_PASSWORD", "x")
    monkeypatch.setattr(config, "MSSQL_DATABASE", "ACME")
    monkeypatch.setattr(config, "SAP_B1_HOST", "", raising=False)
    sources = config.enabled_sources()
    assert sources == ["hana", "mssql", "simulator"], "HANA must lead; unconfigured SL excluded"


def test_partial_configuration_is_not_treated_as_enabled(monkeypatch):
    """A host with no password must not be offered, and a password must not
    silently enable a backend on its own (that was the MSSQL bug)."""
    monkeypatch.setattr(config, "SIMULATOR_ALLOWED", False)
    monkeypatch.setattr(config, "HANA_HOST", "hana.internal")
    monkeypatch.setattr(config, "HANA_USER", "cira_ro")
    monkeypatch.setattr(config, "HANA_SCHEMA", "ACME")
    monkeypatch.setattr(config, "HANA_PASSWORD", "", raising=False)
    monkeypatch.setattr(config, "MSSQL_HOST", "", raising=False)
    monkeypatch.setattr(config, "MSSQL_PASSWORD", "leftover", raising=False)
    assert config.enabled_sources() == []


def test_forcing_an_unconfigured_source_is_fatal(monkeypatch):
    monkeypatch.setattr(config, "DATA_SOURCE", "hana")
    monkeypatch.setattr(config, "HANA_HOST", "", raising=False)
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://cira.corp"], raising=False)
    fatal, _ = config.validate()
    assert any("not enabled" in message for message in fatal)


def test_wildcard_cors_with_strict_mode_is_fatal(monkeypatch):
    monkeypatch.setattr(config, "DATA_SOURCE", "simulator")
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", [], raising=False)
    monkeypatch.setattr(config, "ALLOW_ORIGIN_REGEX", "", raising=False)
    monkeypatch.setattr(config, "STRICT", True, raising=False)
    fatal, _ = config.validate()
    assert any("origin" in message.lower() for message in fatal)


def test_open_demo_modes_are_warned(monkeypatch):
    monkeypatch.setattr(config, "DATA_SOURCE", "simulator")
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://cira.corp"], raising=False)
    monkeypatch.setattr(config, "ALLOW_ANY_EMPLOYEE", True, raising=False)
    _, warnings = config.validate()
    assert any("ANY employee" in message for message in warnings)


def test_summary_does_not_disclose_topology_or_principals():
    summary = config.summary()
    blob = str(summary).lower()
    for key in ("host", "port", "password", "base_url"):
        assert key not in blob, f"/sap/health must not expose {key!r}"
    assert summary["hana"]["configured"] in (True, False)


def test_tenant_registry_resolves_only_known_company_dbs(monkeypatch):
    monkeypatch.setattr(config, "TENANTS", {"ACME_PROD": {"COMPANY_DB": "ACME_PROD"}}, raising=False)
    assert config.tenant_for("ACME_PROD") == {"COMPANY_DB": "ACME_PROD"}
    assert config.tenant_for("SOMETHING_ELSE") is None


def test_tenant_overrides_are_read_from_env(monkeypatch):
    monkeypatch.setenv("CIRA_TENANTS", "ACME_PROD,ACME_LIVE")
    monkeypatch.setenv("CIRA_TENANT_ACME_LIVE_MSSQL_HOST", "db.internal")
    tenants = config.build_tenants()
    assert tenants["ACME_LIVE"]["MSSQL_HOST"] == "db.internal"
    assert tenants["ACME_PROD"] == {"COMPANY_DB": "ACME_PROD"}


def test_writes_are_closed_by_default():
    assert config.SAP_WRITE_ENABLED is False
    assert "admin" in config.SAP_WRITE_ROLES
    assert "Users" not in config.SAP_WRITE_ENTITIES
