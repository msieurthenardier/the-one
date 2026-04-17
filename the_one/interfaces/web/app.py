from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
    llm = get_provider(settings.llm_provider, model=settings.llm_model)
    tools = ToolRegistry()
    tools.load_defaults()
    return Agent(llm=llm, tools=tools)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text()


@app.get("/api/info")
async def info() -> dict[str, Any]:
    return {
        "version": "0.1.0",
        "provider": settings.llm_provider,
        "model": settings.llm_model,
    }


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
