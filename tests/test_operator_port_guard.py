"""The conftest guard against unit tests reaching the operator's ports (M32 F2 L05)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.parametrize("port", [8484, 8485])
def test_sync_httpx_to_operator_ports_is_refused(port):
    with pytest.raises(AssertionError, match="operator's port"):
        httpx.get(f"http://127.0.0.1:{port}/api/live", timeout=0.2)
    with pytest.raises(AssertionError, match="operator's port"):
        httpx.post(f"http://localhost:{port}/api/window/quit", timeout=0.2)


async def test_async_httpx_to_operator_ports_is_refused():
    async with httpx.AsyncClient() as c:
        with pytest.raises(AssertionError, match="operator's port"):
            await c.get("http://127.0.0.1:8484/api/live")


def test_other_ports_are_untouched():
    with pytest.raises(httpx.HTTPError):  # refused connection, not the guard
        httpx.get("http://127.0.0.1:9/api/live", timeout=0.2)
