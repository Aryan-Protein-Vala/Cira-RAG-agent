import json
import asyncio
import httpx
import argparse
import sys
import os

API_URL = os.getenv("API_URL", "http://localhost:8000")
AUTH_DATA = {"email": "aryansharma24112003@gmail.com", "password": "aryan"}
TENANT_ID = os.getenv("CIRA_TENANT_ID", "db_sandbox")

async def get_token():
    async with httpx.AsyncClient(timeout=10.0) as client:
        # First try superadmin login
        try:
            r = await client.post(
                f"{API_URL}/superadmin/login",
                json={"username": AUTH_DATA["email"], "password": AUTH_DATA["password"]}
            )
            if r.status_code == 200:
                return r.json()["token"]
        except Exception:
            pass

        # Fallback to standard employee login
        try:
            r = await client.post(
                f"{API_URL}/auth/login",
                json={"employee_id": "EMP-20481", "password": "any", "company_db": "CIRA_DEMO_NEW"}
            )
            if r.status_code == 200:
                return r.json()["token"]
        except Exception:
            pass

    # If offline / direct token generation is needed
    try:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
        from auth import create_token
        minted = create_token("ADMIN-001", "Administrator", ["admin", "superadmin"], company_db="CIRA_DEMO_NEW")
        return minted["token"]
    except Exception as exc:
        print(f"Failed to obtain token: {exc}")
        sys.exit(1)

async def run_question(client, token, tenant_id, question_data):
    headers = {"Authorization": f"Bearer {token}", "x-tenant-id": tenant_id}
    session_id = f"test_{question_data['id']}"
    body = {
        "query": question_data["question"],
        "session_id": session_id
    }
    
    events = []
    try:
        async with client.stream("POST", f"{API_URL}/chat", headers=headers, json=body, timeout=35.0) as response:
            if response.status_code != 200:
                print(f"Error {response.status_code}: {await response.aread()}")
                return None
                
            buffer = ""
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        events.append(json.loads(data_str))
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        print(f"Exception for Q{question_data['id']}: {e}")
        return None

    # Analyze events according to CIRA agent SSE contract
    final_text = ""
    tools_called = []
    queried_tables = set()
    queried_cols = set()
    
    for ev in events:
        ev_type = ev.get("type")
        if ev_type == "chunk":
            final_text += ev.get("text", "")
        elif ev_type == "status":
            tool = ev.get("tool")
            if tool:
                tools_called.append(tool)
        elif ev_type == "tabular":
            tools_called.append("sap_query")
            meta = ev.get("meta") or {}
            source = meta.get("source") or ""
            if source:
                queried_tables.add(source.upper())
            # Inspect column headers in tabular data
            rows = ev.get("data") or []
            if rows and isinstance(rows, list) and isinstance(rows[0], dict):
                for k in rows[0].keys():
                    queried_cols.add(k)
        elif ev_type == "chart":
            tools_called.append("sap_query")
            
    return {
        "events": events,
        "final_text": final_text,
        "tools_called": tools_called,
        "queried_tables": list(queried_tables),
        "queried_cols": list(queried_cols),
    }

def evaluate_result(question, result):
    if not result:
        return {"pass": False, "reason": "No result returned or connection timeout"}
        
    expected_rejection = bool(
        question.get("expected_rejection")
        or question.get("hallucination_trap")
        or question.get("bucket") == "hallucination"
    )
    expected_clarification = bool(
        question.get("expected_clarification")
        or question.get("bucket") == "ambiguous"
    )
    
    final_text = result["final_text"]
    tools_called = result["tools_called"]
    queried_tables = set(result.get("queried_tables", []))

    # Check for rejection (hallucination bucket)
    if expected_rejection:
        rejection_words = ["not found", "cannot", "do not have", "unable", "sorry", "only answer", "enterprise data", "sap"]
        if not tools_called or any(w in final_text.lower() for w in rejection_words):
            return {"pass": True, "reason": "Correctly rejected or redirected without unauthorized SAP query"}
        return {"pass": False, "reason": "Queried SAP for out-of-scope question and did not reject"}

    # Check for clarification (ambiguous bucket)
    if expected_clarification:
        clarification_markers = ["?", "which", "could you", "please specify", "clarify", "provide", "all or specific"]
        if any(w in final_text.lower() for w in clarification_markers) or not tools_called:
            return {"pass": True, "reason": "Correctly asked for clarification"}
        return {"pass": False, "reason": "Queried SAP without seeking clarification"}

    # Standard queries
    expected_tables = set(question.get("expected_tables", []))
    expected_cols = set(question.get("expected_columns", []))
    
    # Check if tools were called or tables were retrieved
    if not tools_called and not queried_tables:
        # Check if deterministic planner answered directly in text
        if any(tbl.lower() in final_text.lower() for tbl in expected_tables):
            return {"pass": True, "reason": "Answered with expected entity in response"}
        return {"pass": False, "reason": "Did not query SAP and no entity found"}
        
    # Check if ANY expected table was found
    if expected_tables and queried_tables:
        if expected_tables.intersection(queried_tables):
            return {"pass": True, "reason": "Queried correct tables"}
            
    # If final text or event payload returned enterprise data
    if "sap_query" in tools_called or "sap_sql" in tools_called or any(e.get("type") == "tabular" for e in result["events"]):
        return {"pass": True, "reason": "Executed SAP query and streamed data"}

    return {"pass": False, "reason": f"Expected tables {expected_tables} not in {queried_tables}"}

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="sandbox")
    args = parser.parse_args()
    
    suite_path = os.path.join(os.path.dirname(__file__), f"suite_{args.suite}.jsonl")
    if not os.path.exists(suite_path):
        print(f"Suite {suite_path} not found.")
        sys.exit(1)
        
    questions = []
    with open(suite_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))
                
    token = await get_token()
    tenant_id = TENANT_ID
    
    print(f"Running accuracy suite ({len(questions)} questions) against tenant {tenant_id}...")
    
    results = []
    async with httpx.AsyncClient(timeout=35.0) as client:
        for q in questions:
            res = await run_question(client, token, tenant_id, q)
            eval_res = evaluate_result(q, res)
            
            out = {
                "id": q["id"],
                "bucket": q["bucket"],
                "question": q["question"],
                "pass": eval_res["pass"],
                "reason": eval_res["reason"],
                "final_text": (res["final_text"][:200] if res else "")
            }
            results.append(out)
            
            status = "PASS" if eval_res["pass"] else "FAIL"
            print(f"Q{q['id']} [{q['bucket']}]: {status} ({eval_res['reason']})")
            
            # Sleep to prevent hitting OpenRouter free-tier rate limits
            await asyncio.sleep(3)
            
    results_path = os.path.join(os.path.dirname(__file__), "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    passes = sum(1 for r in results if r["pass"])
    print(f"\nCompleted! {passes}/{len(results)} passed ({(passes/len(results))*100:.1f}%). Results saved to results.json")

if __name__ == "__main__":
    asyncio.run(main())
