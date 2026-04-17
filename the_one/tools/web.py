from __future__ import annotations

from typing import Any

import httpx

from the_one.tools.base import Tool


class HttpRequestTool(Tool):
    name = "http_request"
    description = "Make an HTTP request to any URL. Supports GET, POST, PUT, PATCH, DELETE."
    parameters = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "description": "HTTP method.",
            },
            "url": {"type": "string", "description": "The URL to request."},
            "headers": {
                "type": "object",
                "description": "Optional headers.",
                "additionalProperties": {"type": "string"},
            },
            "body": {"type": "string", "description": "Request body (for POST/PUT/PATCH)."},
        },
        "required": ["method", "url"],
    }

    async def execute(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.request(
                    method, url, headers=headers, content=body
                )
                text = resp.text[:10000]
                return f"[{resp.status_code}]\n{text}"
        except Exception as e:
            return f"[error] {e}"


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web using DuckDuckGo and return results. No API key required."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "max_results": {"type": "integer", "description": "Max results (default 5).", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, query: str, max_results: int = 5, **kwargs: Any) -> str:
        try:
            url = "https://html.duckduckgo.com/html/"
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.post(url, data={"q": query})
                # Basic extraction from DDG HTML
                text = resp.text
                results = []
                # Extract result snippets between result__snippet markers
                import re

                snippets = re.findall(
                    r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
                    r'class="result__snippet"[^>]*>(.*?)</span>',
                    text,
                    re.DOTALL,
                )
                for href, title, snippet in snippets[:max_results]:
                    clean_title = re.sub(r"<[^>]+>", "", title).strip()
                    clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()
                    results.append(f"- {clean_title}\n  {href}\n  {clean_snippet}")
                return "\n\n".join(results) if results else "No results found."
        except Exception as e:
            return f"[error] {e}"
