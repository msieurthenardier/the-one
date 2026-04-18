"""
IAAT — Integration and Acceptance Tests

These tests run against the live the-one agent via /api/chat.
They validate that the agent can actually do what it's supposed to do,
end-to-end, with the real LLM, real tools, and real container.

Usage:
    python tests/iaat.py [base_url]
    python tests/iaat.py http://localhost:8484
"""

from __future__ import annotations

import json
import sys
import time
import requests

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8484"
CHAT_URL = f"{BASE_URL}/api/chat"
RESET_URL = f"{BASE_URL}/api/chat/reset"
TIMEOUT = 120  # some tool calls are slow


passed = 0
failed = 0
skipped = 0


def chat(message: str) -> dict:
    """Send a message and return the full response."""
    r = requests.post(CHAT_URL, json={"message": message}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def reset():
    """Reset agent context between tests."""
    requests.post(RESET_URL, timeout=10)
    time.sleep(0.5)


def assistant_text(resp: dict) -> str:
    """Extract concatenated assistant text from response."""
    return "\n".join(
        m.get("content", "") for m in resp.get("messages", []) if m.get("role") == "assistant"
    )


def has_tool_call(resp: dict, name: str | None = None) -> bool:
    """Check if response contains a tool call (optionally by name)."""
    for m in resp.get("messages", []):
        for tc in m.get("tool_calls", []):
            if name is None or tc.get("name") == name:
                return True
    return False


def has_tool_result(resp: dict, substring: str | None = None) -> bool:
    """Check if response contains a tool result (optionally containing substring)."""
    for m in resp.get("messages", []):
        if m.get("role") == "tool":
            if substring is None:
                return True
            if substring.lower() in m.get("content", "").lower():
                return True
    return False


def test(name: str, fn):
    global passed, failed, skipped
    reset()
    print(f"  {name} ... ", end="", flush=True)
    try:
        fn()
        print("PASS")
        passed += 1
    except AssertionError as e:
        print(f"FAIL: {e}")
        failed += 1
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        failed += 1


# ── Tests ────────────────────────────────────────────────────────────────


def test_health():
    """Service is up and responding."""
    r = requests.get(f"{BASE_URL}/api/info", timeout=10)
    r.raise_for_status()
    data = r.json()
    assert "version" in data, f"missing version in {data}"
    assert "model" in data, f"missing model in {data}"


def test_basic_chat():
    """Agent responds to a simple message."""
    resp = chat("What is 2 + 2? Reply with just the number.")
    text = assistant_text(resp)
    assert "4" in text, f"expected '4' in response, got: {text[:200]}"


def test_tool_use_file_read():
    """Agent can read a file using a tool."""
    resp = chat("Read the file /workspace/pyproject.toml and tell me the project name.")
    text = assistant_text(resp)
    # Should have used a tool and found the project name
    assert has_tool_result(resp), f"expected a tool result in response"
    assert "the-one" in text.lower() or "the_one" in text.lower(), \
        f"expected project name in response, got: {text[:200]}"


def test_git_status():
    """Agent can run git status (no dubious ownership error)."""
    resp = chat("Run git status on the workspace. Use the git tool with args 'status'.")
    has_git = has_tool_call(resp, "git") or has_tool_result(resp)
    text = assistant_text(resp)
    full = json.dumps(resp)
    assert "dubious" not in full.lower(), "git dubious ownership error still present"
    assert has_git or "clean" in text.lower() or "modified" in text.lower() or "changes" in text.lower(), \
        f"expected git status output, got: {text[:300]}"


def test_reset():
    """Context reset works — agent forgets previous conversation."""
    chat("Remember this secret code: PINEAPPLE42")
    reset()
    resp = chat("What was the secret code I told you?")
    text = assistant_text(resp)
    assert "PINEAPPLE42" not in text, f"agent remembered after reset: {text[:200]}"


def test_run_tests():
    """Agent can run the test suite."""
    resp = chat("Run the tests using the run_tests tool.")
    full = json.dumps(resp)
    assert has_tool_result(resp) or has_tool_call(resp, "run_tests"), \
        f"expected run_tests tool usage"
    assert "error" not in full.lower() or "passed" in full.lower(), \
        f"tests may have failed: {full[:500]}"


def test_self_awareness():
    """Agent knows it's 'the-one' and can describe its own architecture."""
    resp = chat("What is your name and what directory is your source code in?")
    text = assistant_text(resp)
    assert "the-one" in text.lower() or "the_one" in text.lower(), \
        f"agent doesn't know its name: {text[:200]}"


def test_direct_action_restart():
    """Direct-action pattern matches restart intent.
    Actually triggering it would kill the container, so we test via
    a benign message right after to confirm the agent is still alive
    (meaning the pattern didn't fire for a non-matching input)."""
    # This should NOT trigger a restart — agent should respond normally
    resp = chat("how do I restart my computer?")
    text = assistant_text(resp)
    assert len(text) > 0, "agent didn't respond to non-restart question"
    # If we got here, the agent is still alive — pattern didn't false-positive


# ── Runner ───────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print(f"\nIAAT — Integration and Acceptance Tests")
    print(f"Target: {BASE_URL}\n")

    # Verify service is reachable first
    try:
        test_health()
        print(f"  health check ... PASS")
        passed += 1
    except Exception as e:
        print(f"  health check ... FAIL: {e}")
        print(f"\nAgent is not reachable at {BASE_URL}. Aborting.")
        sys.exit(1)

    test("basic chat", test_basic_chat)
    test("tool use (file read)", test_tool_use_file_read)
    test("git status (no dubious ownership)", test_git_status)
    test("context reset", test_reset)
    test("run tests", test_run_tests)
    test("self-awareness", test_self_awareness)
    # restart pattern test last — doesn't hit the live agent
    test("direct-action: no false positive", test_direct_action_restart)

    print(f"\n{'='*50}")
    print(f"  {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'='*50}\n")
    sys.exit(1 if failed else 0)
