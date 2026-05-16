"""Import-graph regression tests.

Locks the F6 L0 chain-break: importing the_one.agent.core does NOT
transitively load the_one.mcp.oauth. The oauth surface is still
reachable for callers who explicitly import it.

Subprocess-isolated because pytest's own import machinery contaminates
sys.modules; assertions on sys.modules under the same interpreter
would see pollution from earlier-running tests.
"""

import subprocess
import sys


def _run_in_subprocess(script: str) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def test_import_agent_core_does_not_load_mcp_oauth() -> None:
    """F6 L0: chain break — agent.core lazy-import retirement does NOT
    drag in mcp.oauth via the canonical-MCPAuthRequired-at-mcp.errors
    path.
    """
    script = (
        "import sys; "
        "import the_one.agent.core; "
        "leaked = sorted(k for k in sys.modules if k.startswith('the_one.mcp.oauth')); "
        "assert leaked == [], f'mcp.oauth leaked: {leaked}'; "
        "print('OK')"
    )
    rc, out, err = _run_in_subprocess(script)
    assert rc == 0, f"subprocess failed:\nstdout={out}\nstderr={err}"
    assert "OK" in out


def test_import_mcp_oauth_still_loads_storage() -> None:
    """Negative: explicit oauth import still loads the storage chain.
    Locks that the chain exists for callers who legitimately need oauth
    surfaces (e.g. provider_factory).
    """
    script = (
        "import sys; "
        "import the_one.mcp.oauth; "
        "assert 'the_one.mcp.oauth.storage' in sys.modules; "
        "assert 'the_one.db.repositories' in sys.modules; "
        "print('OK')"
    )
    rc, out, err = _run_in_subprocess(script)
    assert rc == 0, f"subprocess failed:\nstdout={out}\nstderr={err}"
    assert "OK" in out
