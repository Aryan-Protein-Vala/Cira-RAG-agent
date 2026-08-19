"""Exercise the real LangGraph/LLM path without a paid API key.

A tiny OpenAI-compatible server stands in for OpenRouter: the first turn
returns a `sap_query` tool call, the second turn returns the executive summary
(plus a markdown table that CIRA must suppress).  This proves that

* tools are registered and callable by the model,
* tool results reach the ResultBus and become `tabular` + `chart` SSE events,
* the streamed prose is filtered so raw data never appears twice,
* the LLM never receives the full 500-row payload.
"""

import importlib
import json
import os
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

pytestmark = pytest.mark.asyncio

seen_prompts: list[dict] = []


def _chunk(delta: dict, finish: str | None = None) -> str:
    payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "mock/model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def build_mock_openai() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completions(request: Request):
        body = await request.json()
        seen_prompts.append(body)
        messages = body.get("messages", [])
        already_called = any(m.get("role") == "tool" for m in messages)

        def stream():
            if not already_called:
                yield _chunk(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "sap_query",
                                    "arguments": json.dumps(
                                        {
                                            "table": "invoices",
                                            "filters": [
                                                {"column": "DocStatus", "op": "eq", "value": "Open"}
                                            ],
                                            "limit": 50,
                                        }
                                    ),
                                },
                            }
                        ],
                    }
                )
                yield _chunk({}, "tool_calls")
            else:
                for text in [
                    "You have open invoices worth a significant amount. ",
                    "The top customer accounts for the largest share.\n",
                    "| DocNum | CardName |\n",
                    "|---|---|\n",
                    "| 5001 | Acme |\n",
                ]:
                    yield _chunk({"content": text})
                yield _chunk({}, "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


@pytest.fixture(scope="module")
def mock_llm():
    app = build_mock_openai()
    config = uvicorn.Config(app, host="127.0.0.1", port=8931, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield "http://127.0.0.1:8931/v1"
    server.should_exit = True
    thread.join(timeout=5)


async def test_agent_uses_tools_and_streams_visuals(mock_llm):
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    os.environ["OPENROUTER_BASE_URL"] = mock_llm
    os.environ["CIRA_MODEL"] = "mock/model"

    import config

    importlib.reload(config)
    import agent

    importlib.reload(agent)
    assert agent.llm is not None, "the LLM path must be active for this test"

    events = []
    async for raw in agent.stream_chat_query("Show me open invoices", [], employee_id="EMP-1"):
        events.append(json.loads(raw[len("data: "):]))

    kinds = [e["type"] for e in events]
    assert "status" in kinds          # "Querying SAP Business One…"
    assert "tabular" in kinds         # dataset streamed to the UI
    assert "chart" in kinds
    assert kinds[-1] == "done"

    table = next(e for e in events if e["type"] == "tabular")
    assert table["entity"] == "OINV"
    assert len(table["data"]) > 0
    assert all(row["DocStatus"] == "Open" for row in table["data"])

    # The prose keeps the summary but drops the markdown table rows
    prose = "".join(e["text"] for e in events if e["type"] == "chunk")
    assert "open invoices" in prose.lower()
    assert "| 5001 |" not in prose

    # The model must never be handed the whole result set
    tool_messages = [
        m for body in seen_prompts for m in body.get("messages", []) if m.get("role") == "tool"
    ]
    assert tool_messages, "the tool result should be fed back to the model"
    payload = json.loads(tool_messages[-1]["content"])
    assert payload["rows_returned"] > len(payload["sample_rows"])
    assert len(payload["sample_rows"]) <= 8
    assert payload["totals"]

    # Restore no-LLM mode for the rest of the suite
    os.environ["OPENROUTER_API_KEY"] = ""
    importlib.reload(config)
    importlib.reload(agent)


async def test_tool_errors_are_returned_to_the_model_not_raised():
    import agent

    bus = agent.ResultBus()
    tools = {t.name: t for t in agent.make_tools(bus, "q", "EMP-1")}
    result = await tools["sap_query"].ainvoke({"table": "TOTALLY_UNKNOWN_TABLE"})
    assert result["ok"] is False
    assert "does not exist" in result["error"].lower() or "unknown" in result["error"].lower()
    assert "hint" in result


async def test_policy_tool_searches_real_documents():
    import agent

    bus = agent.ResultBus()
    tools = {t.name: t for t in agent.make_tools(bus, "q", "EMP-1")}
    result = await tools["query_company_docs"].ainvoke({"query": "hotel cap per night"})
    assert result["ok"]
    assert result["matches"]
    assert "250" in result["matches"][0]["content"]
