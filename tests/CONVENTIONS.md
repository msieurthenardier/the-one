# Test conventions

Cross-cutting test patterns established during F2 (Cross-Platform Foundations).
New tests should reuse these patterns rather than reinvent them.

---

## 1. asyncio_mode = "auto"

`pyproject.toml` sets `[tool.pytest.ini_options] asyncio_mode = "auto"`. Async
tests are written as plain `async def test_x():` — no `@pytest.mark.asyncio`
decorator needed. pytest-asyncio applies the marker automatically.

```python
async def test_read_file_happy(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hi")
    result = await ReadFileTool().execute(path=str(f))
    assert "hi" in result
```

---

## 2. monkeypatch.setenv("HOME", str(tmp_path))

Tests that rely on `~` expansion or `Path.home()` set HOME to a tmp_path so
the tilde resolves into an isolated test directory. Avoid `Path.home()`-stub
patterns; the env-var approach interacts correctly with `expanduser()` calls
deep inside platform helpers.

```python
async def test_read_under_tilde(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "doc.txt"
    target.write_text("contents")
    result = await ReadFileTool().execute(path="~/doc.txt")
    assert "contents" in result
```

---

## 3. httpx MockTransport with _install_mock recursion-avoidance

Web tool tests inject controlled HTTP responses via `httpx.MockTransport`.
Capture `original = httpx.AsyncClient` BEFORE `monkeypatch.setattr` so the
factory's call to `original(...)` does not recurse through the patched symbol.

```python
def _install_mock(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient   # capture before patch

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return original(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


async def test_http_get_200(monkeypatch):
    def handler(req):
        return httpx.Response(200, text="hello")
    _install_mock(monkeypatch, handler)
    result = await HttpRequestTool().execute(method="GET", url="https://x.test/")
    assert result.startswith("[200]") and "hello" in result
```

---

## 4. kill+reap timeout-budget assertions

Tests that exercise process timeout paths assert the kill+reap returns within
a small wall-clock budget — broken kill+reap blocks for the full underlying
sleep. Use `time.monotonic()` deltas, not framework timers.

```python
import time

async def test_shell_timeout_kills_fast(monkeypatch):
    start = time.monotonic()
    result = await ShellTool().execute(command="sleep 5", timeout_seconds=0.5)
    elapsed = time.monotonic() - start
    assert elapsed < 3.0, f"kill+reap blocked: {elapsed}s"
    assert "[error]" in result
```

The 3-second budget is intentionally generous (CI scheduler latency);
typical local runs see <1s. A regression in the kill+reap path manifests
as a 5s+ test — the assertion catches it before the runtime explodes.
