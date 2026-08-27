"""Connection + configuration diagnostic. Run this BEFORE blaming the app.

    python scripts/diagnose.py            # human-readable report
    python scripts/diagnose.py --json     # machine-readable
    python scripts/diagnose.py --require-live   # exit 1 unless a real ERP answered

Reads Backend/.env through config.py so there is exactly one source of truth for
host/port/credentials — nothing is hard-coded here any more.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

try:
    import config
except ImportError as exc:  # pragma: no cover
    print(f"Cannot import Backend/config.py: {exc}")
    raise SystemExit(2)

results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "ok": bool(ok), "detail": detail[:300]})
    mark = "[ OK ]" if ok else "[FAIL]"
    print(f"  {mark} {name}" + (f" — {detail[:200]}" if detail else ""))


def tcp(host: str, port: int, timeout: float = 4.0) -> tuple[bool, str]:
    if not host:
        return False, "not configured"
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port} reachable"
    except Exception as exc:
        return False, f"{host}:{port}: {exc.__class__.__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-live", action="store_true")
    args = parser.parse_args()

    def report():
        if args.json:
            print(json.dumps({"checks": results}, indent=2))

    if not args.json:
        print("=" * 72)
        print("  CIRA DIAGNOSTIC")
        print("=" * 72)

    fatal, warnings = config.validate()
    print("\n[1] Configuration")
    for problem in fatal:
        check("config", False, problem)
    for note in warnings:
        check("config note", True, note)
    if not fatal and not warnings:
        check("config", True, "no problems found")
    print(f"  sources enabled: {config.enabled_sources() or 'NONE'}")

    print("\n[2] SAP HANA")
    if config.HANA_HOST:
        ok, detail = tcp(config.HANA_HOST, config.HANA_PORT)
        check("hana tcp", ok, detail)
        if ok:
            try:
                from sap.hana_backend import HanaBackend

                probe = HanaBackend().ping(force=True)
                check("hana login+schema", probe.get("ok", False), str(probe.get("error") or probe.get("schema")))
            except Exception as exc:
                check("hana login+schema", False, str(exc))
    else:
        check("hana", False, "HANA_HOST not configured (this is the primary source)")

    print("\n[3] SQL Server (only if B1 runs on MS SQL)")
    if config.MSSQL_HOST:
        ok, detail = tcp(config.MSSQL_HOST, config.MSSQL_PORT)
        check("mssql tcp", ok, detail)
    else:
        print("  [skip] MSSQL_HOST not configured")

    print("\n[4] SAP B1 Service Layer")
    if config.SAP_B1_HOST:
        ok, detail = tcp(config.SAP_B1_HOST, config.SAP_B1_PORT)
        check("service layer tcp", ok, detail)
    else:
        print("  [skip] SAP_B1_HOST not configured")

    print("\n[5] LLM provider")
    if config.OPENROUTER_API_KEY:
        try:
            import httpx

            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{config.OPENROUTER_BASE_URL.rstrip('/')}/auth/key",
                    headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
                )
            check("openrouter key", resp.status_code == 200, f"HTTP {resp.status_code}")
        except Exception as exc:
            check("openrouter key", False, str(exc))
    else:
        print("  [skip] no OPENROUTER_API_KEY — the deterministic planner answers instead")

    print("\n[6] What CIRA would actually use right now")
    import asyncio

    from sap import router as sap_router

    try:
        info = asyncio.run(sap_router.health(force=True))
        check(
            "active backend",
            not info.get("simulated"),
            f"{info.get('active_backend')} · schema={info.get('schema')} · "
            f"tables={info.get('tables_visible')}",
        )
        for attempt in info.get("attempts", []):
            check(f"  candidate {attempt.get('candidate')}", bool(attempt.get("ok")),
                  str(attempt.get("error") or "ok"))
        if info.get("simulated"):
            print("  ⚠ SANDBOX DATA — answers are labelled SIMULATED, not your ERP.")
            print("    Common causes: wrong port (tenant DBs listen on 3xx15),")
            print("    firewall/NSG not open, HANA_ENCRYPT mismatch, missing SELECT grants.")
        live = not info.get("simulated")
    except Exception as exc:
        check("active backend", False, str(exc))
        live = False

    report()
    if args.require_live and not live:
        print("\n--require-live: no live SAP source answered.")
        return 1
    return 1 if fatal else 0


if __name__ == "__main__":
    raise SystemExit(main())
