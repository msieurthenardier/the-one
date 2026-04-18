from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from the_one.agent import Agent
from the_one.config import settings
from the_one.llm import get_provider
from the_one.llm.base import Role
from the_one.tools.base import ToolRegistry

app = FastAPI(title="the-one")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _make_agent() -> Agent:
    settings.ensure_dirs()
    llm = get_provider(
        settings.llm_provider, model=settings.llm_model, base_url=settings.llm_base_url
    )
    tools = ToolRegistry()
    tools.load_defaults()
    return Agent(llm=llm, tools=tools)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text()


@app.get("/api/info")
async def info() -> dict[str, Any]:
    import json as _json

    result: dict[str, Any] = {
        "version": "0.1.0",
        "provider": settings.llm_provider,
        "model": settings.llm_model,
    }

    # Include deploy status if available
    status_file = settings.workspace_dir / ".deploy-status.json"
    if status_file.exists():
        try:
            result["deploy"] = _json.loads(status_file.read_text())
        except Exception:
            pass

    return result


_chat_agent: Agent | None = None


def _get_chat_agent() -> Agent:
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = _make_agent()
    return _chat_agent


@app.post("/api/chat")
async def chat(request: Request) -> dict[str, Any]:
    """Synchronous chat endpoint for programmatic access (e.g. Claude Code)."""
    payload = await request.json()
    user_input = payload.get("message", "")
    if not user_input:
        return {"error": "no message provided"}

    agent = _get_chat_agent()

    if user_input == "/reset":
        agent.reset()
        return {"messages": [{"role": "system", "content": "Context cleared."}]}

    result_messages: list[dict[str, Any]] = []
    async for msg in agent.step(user_input):
        if msg.role == Role.ASSISTANT:
            entry: dict[str, Any] = {"role": "assistant"}
            if msg.content:
                entry["content"] = msg.content
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {"name": tc.name, "arguments": tc.arguments}
                    for tc in msg.tool_calls
                ]
            result_messages.append(entry)
        elif msg.role == Role.TOOL and msg.tool_result:
            result_messages.append({
                "role": "tool",
                "content": msg.tool_result.content[:4000],
                "is_error": msg.tool_result.is_error,
            })

    return {"messages": result_messages}


@app.post("/api/chat/reset")
async def chat_reset() -> dict[str, str]:
    """Reset the persistent chat agent's context."""
    agent = _get_chat_agent()
    agent.reset()
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    agent = _make_agent()

    try:
        while True:
            data = await ws.receive_text()
            payload = json.loads(data)
            user_input = payload.get("message", "")

            if not user_input:
                continue

            if user_input == "/reset":
                agent.reset()
                await ws.send_json({"type": "system", "content": "Context cleared."})
                continue

            async for msg in agent.step(user_input):
                if msg.role == Role.ASSISTANT:
                    if msg.content:
                        await ws.send_json({"type": "assistant", "content": msg.content})
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            await ws.send_json({
                                "type": "tool_call",
                                "name": tc.name,
                                "arguments": tc.arguments,
                            })
                elif msg.role == Role.TOOL and msg.tool_result:
                    await ws.send_json({
                        "type": "tool_result",
                        "content": msg.tool_result.content[:2000],
                        "is_error": msg.tool_result.is_error,
                    })

            await ws.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass
