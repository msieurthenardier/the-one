"""Tool-level redirect-hop host-list tests (sortie 07 leg 3, DD15).

Each web tool goes through its own real ``_build_transport`` (so the lists
are proven wired), with the network replaced by ``_patch_getaddrinfo`` and
``_patch_super_dispatch``. A 3xx from an allowed host to a refused host is
reported as the tool's ``[error] [constraint] ...`` shape, with no request
sent for the refused hop.
"""

from __future__ import annotations

import socket

import httpx
import pytest

from tests.test_web_helpers import _patch_getaddrinfo, _patch_super_dispatch, _Recorder
from the_one.tools._web_config import WebConfig
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools.resolver import NO_HOSTS
from the_one.tools.web import DownloadFileTool, FetchUrlTool, HttpRequestTool

_ADDR = [[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 80))]]


def _setup(monkeypatch) -> _Recorder:
    _patch_getaddrinfo(monkeypatch, _ADDR)
    rec = _Recorder()
    rec.response_factory = lambda req: httpx.Response(
        302, headers={"Location": "http://other.example/x"}
    )
    _patch_super_dispatch(monkeypatch, rec)
    return rec


def _tool(kind: str, cfg: WebConfig, tmp_path):
    if kind == "http_request":
        return HttpRequestTool(cfg), {"method": "GET", "url": "http://a.example/"}
    if kind == "fetch_url":
        return FetchUrlTool(cfg), {"url": "http://a.example/"}
    fs = FilesystemConfig(path_allowlist=[str(tmp_path)])
    return (
        DownloadFileTool(cfg, cross_configs={FilesystemConfig: fs}),
        {"url": "http://a.example/", "path": str(tmp_path / "out.bin")},
    )


KINDS = ["http_request", "fetch_url", "download_file"]


@pytest.mark.parametrize("kind", KINDS)
async def test_hop_outside_allowlist_refused(kind, monkeypatch, tmp_path) -> None:
    rec = _setup(monkeypatch)
    tool, args = _tool(kind, WebConfig(host_allowlist=["a.example"]), tmp_path)
    result = await tool.execute(**args)
    assert result.startswith("[error] [constraint]")
    assert "other.example" in result and "host_allowlist" in result
    assert len(rec.requests) == 1
    assert not (tmp_path / "out.bin").exists()


@pytest.mark.parametrize("kind", KINDS)
async def test_hop_in_denylist_refused(kind, monkeypatch, tmp_path) -> None:
    rec = _setup(monkeypatch)
    tool, args = _tool(kind, WebConfig(host_denylist=["other.example"]), tmp_path)
    result = await tool.execute(**args)
    assert result.startswith("[error] [constraint]")
    assert "other.example" in result and "host_denylist" in result
    assert len(rec.requests) == 1


@pytest.mark.parametrize("kind", KINDS)
async def test_no_hosts_refuses_every_host(kind, monkeypatch, tmp_path) -> None:
    rec = _setup(monkeypatch)
    tool, args = _tool(kind, WebConfig(host_allowlist=[NO_HOSTS]), tmp_path)
    result = await tool.execute(**args)
    assert result.startswith("[error] [constraint]")
    assert "no hosts are allowed" in result
    assert rec.requests == []
