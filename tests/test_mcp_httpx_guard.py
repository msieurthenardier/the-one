"""DD4 guard: everything under ``the_one/mcp/`` runs on ``httpx2``, never ``httpx``.

mcp 2.x is built on the separate ``httpx2`` package, while ``httpx`` stays
importable (the rest of the app uses it), so a leftover ``except httpx.HTTPError``
or ``httpx.Auth`` annotation under the MCP package would fail silently instead of
loudly. This AST test fails on any ``import httpx`` / ``from httpx ...`` there and
does NOT flag ``httpx2``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests import _source_scan

MCP_DIR = Path(__file__).resolve().parent.parent / "the_one" / "mcp"


def _httpx_imports(source: str) -> list[int]:
    hits: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(a.name == "httpx" or a.name.startswith("httpx.") for a in node.names):
                hits.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "httpx" or node.module.startswith("httpx.")):
                hits.append(node.lineno)
    return hits


def test_the_guard_flags_httpx_but_not_httpx2() -> None:
    assert _httpx_imports("import httpx") == [1]
    assert _httpx_imports("import httpx.something as h") == [1]
    assert _httpx_imports("from httpx import AsyncClient") == [1]
    assert _httpx_imports("from httpx._client import Client") == [1]
    assert _httpx_imports("import httpx2") == []
    assert _httpx_imports("import httpx2 as h\nfrom httpx2 import AsyncClient") == []
    assert _httpx_imports("from httpx2._client import X") == []
    # a string or comment mentioning httpx is not an import
    assert _httpx_imports('x = "import httpx"  # import httpx') == []


def test_no_module_under_the_one_mcp_imports_httpx() -> None:
    offenders: dict[str, list[int]] = {}
    files = sorted(MCP_DIR.rglob("*.py"))
    assert files, "the_one/mcp/ not found"
    for path in files:
        hits = _httpx_imports(path.read_text(encoding="utf-8"))
        if hits:
            offenders[str(path.relative_to(MCP_DIR.parent.parent))] = hits
    assert offenders == {}, f"use httpx2 under the_one/mcp/ (DD4): {offenders}"


def test_the_two_oauth_flow_drivers_in_api_use_httpx2() -> None:
    """The two OAuth flow drivers hand the SDK's provider (an ``httpx2.Auth``) to a
    client, so they must build an ``httpx2.AsyncClient``; ``api.py`` keeps ``httpx``
    for its non-MCP uses. One driver is ``mcp_oauth_flow.py`` (the chat sign-in flow, moved out
    of ``api.py`` in sortie 22); the other is ``mcp_connection_flow.py``, which reaches ``httpx2``
    as ``_api.httpx2`` so a patch on ``api.httpx2`` still applies."""
    web = MCP_DIR.parent / "interfaces" / "web"
    auth_clients: list[str] = []
    for name in ("mcp_oauth_flow.py", "mcp_connection_flow.py"):
        tree = ast.parse((web / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "AsyncClient"
                and any(kw.arg == "auth" for kw in node.keywords)
            ):
                target = node.func.value
                if isinstance(target, ast.Name):
                    auth_clients.append(target.id)
                elif isinstance(target, ast.Attribute):
                    auth_clients.append(target.attr)
    assert auth_clients == ["httpx2", "httpx2"]


# --- AC2: no code (imports or names) uses the removed mcp 1.x surface ------------

_REMOVED_MODULES = ("mcp.server.fastmcp", "mcp.shared.version")
_REMOVED_NAMES = {"McpError", "FastMCP"}


def _removed_surface_uses(source: str) -> list[str]:
    hits: list[str] = []
    # Every hit below spells one of these words in the source text (a module path or a name),
    # so a file without any of them has none: skip its AST (exact pre-filter, M34 F1 L01).
    if not any(word in source for word in (*_REMOVED_MODULES, *_REMOVED_NAMES)):
        return hits
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in _REMOVED_MODULES or a.name.startswith(
                    tuple(m + "." for m in _REMOVED_MODULES)
                ):
                    hits.append(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module in _REMOVED_MODULES or node.module.startswith(
                tuple(m + "." for m in _REMOVED_MODULES)
            ):
                hits.append(node.module)
            hits.extend(a.name for a in node.names if a.name in _REMOVED_NAMES)
        elif isinstance(node, ast.Name) and node.id in _REMOVED_NAMES:
            hits.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in _REMOVED_NAMES:
            hits.append(node.attr)
    return hits


def test_the_removed_surface_guard_is_code_only() -> None:
    assert _removed_surface_uses("from mcp.server.fastmcp import FastMCP") != []
    assert _removed_surface_uses("from mcp.shared.version import X") != []
    assert _removed_surface_uses("from mcp.shared.exceptions import McpError") != []
    assert _removed_surface_uses("raise McpError(x)") != []
    # prose in comments and strings is not code
    assert _removed_surface_uses("# McpError and FastMCP were removed\nx = 'McpError'") == []
    assert _removed_surface_uses("from mcp.shared.exceptions import MCPError") == []


def test_the_prefilter_never_skips_a_planted_violation(tmp_path: Path) -> None:
    """Each removed module and name, planted alone in a file, is reported (squawk 0306)."""
    planted = {
        "mod_a.py": "import mcp.server.fastmcp\n",
        "mod_b.py": "from mcp.shared.version import X\n",
        "name_a.py": "def f(e):\n    raise McpError(e)\n",
        "name_b.py": "x = FastMCP()\n",
    }
    for name, source in planted.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        assert _removed_surface_uses(_source_scan.text(path)) != [], name
    assert _removed_surface_uses("x = 1\n") == []


def test_no_code_uses_mcp_1x_only_names() -> None:
    root = MCP_DIR.parent.parent
    offenders: dict[str, list[str]] = {}
    me = Path(__file__).resolve()
    for base in ("the_one", "tests"):
        for path in _source_scan.py_files(root / base):
            if path.resolve() == me:
                continue
            hits = _removed_surface_uses(_source_scan.text(path))
            if hits:
                offenders[str(path.relative_to(root))] = hits
    assert offenders == {}, f"mcp 1.x-only surface still used: {offenders}"
