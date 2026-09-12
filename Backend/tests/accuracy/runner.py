import json
import asyncio
import httpx
import argparse
import sys
import os

API_URL = "http://localhost:8000"
# Use superadmin credentials for testing
AUTH_DATA = {"email": "aryansharma24112003@gmail.com", "password": "aryan"}
TENANT_ID = "db_sandbox"

async def get_token():
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{API_URL}/superadmin/login", json={"username": AUTH_DATA["email"], "password": AUTH_DATA["password"]})
        if r.status_code != 200:
            print("Failed to get token:", r.text)
            sys.exit(1)
        return r.json()["token"]

async def run_question(client, token, tenant_id, question_data):
    headers = {"Authorization": f"Bearer {token}", "x-tenant-id": tenant_id}
    
    # We create a new session for each question to avoid context pollution
    session_id = f"test_{question_data['id']}"
    
    body = {
        "query": question_data["question"],
        "session_id": session_id
    }
    
    events = []
    try:
        async with client.stream("POST", f"{API_URL}/chat", headers=headers, json=body, timeout=30.0) as response:
            if response.status_code != 200:
                print(f"Error {response.status_code}: {await response.aread()}")
                return None
                
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        events.append(json.loads(data_str))
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        print(f"Exception for Q{question_data['id']}: {e}")
        return None

    # Analyze events
    final_text = ""
    tools_called = []
    sap_queries = []
    
    for ev in events:
        if ev["type"] == "text":
            final_text += ev["content"]
        elif ev["type"] == "action":
            tools_called.append(ev["tool"])
            if ev["tool"] == "sap_query":
                try:
                    # Depending on how arguments are sent
                    args = json.loads(ev["arguments"]) if isinstance(ev["arguments"], str) else ev["arguments"]
                    sap_queries.append(args)
                except:
                    pass
                
    return {
        "events": events,
        "final_text": final_text,
        "tools_called": tools_called,
        "sap_queries": sap_queries
    }

def evaluate_result(question, result):
    if not result:
        return {"pass": False, "reason": "No result returned"}
        
    expected_rejection = question.get("expected_rejection", False)
    expected_clarification = question.get("expected_clarification", False)
    
    # Check for rejection (hallucination bucket)
    if expected_rejection:
        # If it queried SAP, it might have failed the trap, unless it rejected afterwards
        if "sap_query" in result["tools_called"] and not result["sap_queries"]: 
            # some empty queries? 
            pass
            
        # Simplistic check: If it didn't call tools and gave text, it's likely a rejection
        # But if it confidently answered, we'd need an LLM to grade if it's a rejection.
        # For MVP, let's assume if it queried SAP for something clearly non-SAP it failed.
        if "sap_query" in result["tools_called"]:
            # If it tried to query, let's see if the final text contains rejection keywords
            rejection_words = ["not found", "cannot", "do not have", "unable", "sorry"]
            if any(w in result["final_text"].lower() for w in rejection_words):
                return {"pass": True, "reason": "Correctly rejected (after search)"}
            return {"pass": False, "reason": "Queried SAP and did not reject"}
        
        return {"pass": True, "reason": "Correctly rejected without querying"}

    # Check for clarification (ambiguous bucket)
    if expected_clarification:
        if "sap_query" not in result["tools_called"]:
            return {"pass": True, "reason": "Correctly asked for clarification"}
        return {"pass": False, "reason": "Queried SAP without clarifying"}

    # Standard queries
    if "sap_query" not in result["tools_called"]:
        return {"pass": False, "reason": "Did not query SAP"}
        
    # Check if the expected tables were queried
    expected_tables = set(question.get("expected_tables", []))
    expected_cols = set(question.get("expected_columns", []))
    
    queried_tables = set()
    queried_cols = set()
    
    for sq in result["sap_queries"]:
        queried_tables.add(sq.get("table", "").upper())
        # Also check columns
        for c in sq.get("columns", []):
            queried_cols.add(c)
        for f in sq.get("filters", []):
            queried_cols.add(f.get("column", ""))
        for g in sq.get("group_by", []):
            queried_cols.add(g)
        for a in sq.get("aggregates", []):
            queried_cols.add(a.get("column", ""))
            
    # For MVP, we check if AT LEAST ONE expected table was queried.
    # Because agent might query OCRD instead of OINV if it's looking for a customer first.
    if not expected_tables.intersection(queried_tables):
        return {"pass": False, "reason": f"Expected tables {expected_tables} not in {queried_tables}"}
        
    # Optional: check columns
    if expected_cols and not expected_cols.intersection(queried_cols):
        return {"pass": False, "reason": f"Expected columns {expected_cols} not in {queried_cols}"}

    return {"pass": True, "reason": "Queried correct tables/columns"}

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="sandbox")
    args = parser.parse_args()
    
    suite_path = os.path.join(os.path.dirname(__file__), f"suite_{args.suite}.jsonl")
    if not os.path.exists(suite_path):
        print(f"Suite {suite_path} not found.")
        sys.exit(1)
        
    questions = []
    with open(suite_path, "r") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))
                
    token = await get_token()
    
    # We will need a mock tenant if db_sandbox doesn't exist, but let's assume we use whatever tenant is available.
    # Fetch first tenant
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_URL}/superadmin/tenants", headers={"Authorization": f"Bearer {token}"})
        tenants = r.json()
        if not tenants:
            print("No tenants found! Please create a tenant first.")
            sys.exit(1)
        tenant_id = tenants[0]["company_db"]
        
    print(f"Running accuracy suite against tenant {tenant_id}...")
    
    results = []
    async with httpx.AsyncClient() as client:
        for i, q in enumerate(questions):
            print(f"Running Q{q['id']}: {q['question']}")
            res = await run_question(client, token, tenant_id, q)
            eval_res = evaluate_result(q, res)
            
            out = {
                "id": q["id"],
                "bucket": q["bucket"],
                "question": q["question"],
                "pass": eval_res["pass"],
                "reason": eval_res["reason"],
                "final_text": res["final_text"] if res else ""
            }
            results.append(out)
            
            status = "PASS" if eval_res["pass"] else "FAIL"
            print(f" -> {status} ({eval_res['reason']})")
            
    # Save results
    with open(os.path.join(os.path.dirname(__file__), "results.json"), "w") as f:
        json.dump(results, f, indent=2)
        
    print("Done! Results saved to results.json")

if __name__ == "__main__":
    asyncio.run(main())
