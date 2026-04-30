# Leg: 04-download-file-tool

**Status**: landed
**Flight**: [Web Expansion & Constraints](../flight.md)

## Objective

Add `DownloadFileTool` to `the_one/tools/web.py`. `Config = WebConfig`, `Requires = (FilesystemConfig,)`. Streaming download via `httpx.AsyncClient.stream()`, write to a path validated through `_filesystem_check(path, fs_cfg, mode=CheckMode.WRITE_EXISTING_PARENT)` (post-L0). Mid-stream size-cap abort: track bytes written; if exceeds `cfg.response_size_cap_bytes`, raise `ConstraintError`, unlink the partial file, return `[error] [constraint] response exceeded N bytes; partial file removed`. Four-clause envelope. Registers in `_TOOL_CLASSES` (post-L4 count: 19 tools).

## Context

- **L0 + L1 + L2 + L3 landed** (uncommitted). `WebConfig` ships; `_filesystem_check(path, cfg, mode)` is the unified dispatcher; `SSRFGuardedTransport` is in place; `FetchUrlTool` mirrors L2's `_build_transport` test seam.
- **F5 Decision 5** (`download_file` path semantics): accepts both absolute and relative paths; relative resolves against process cwd via `_filesystem_check(mode=WRITE_NEW)`. Refused if outside `FilesystemConfig.path_allowlist`.
- **Cross-Config dispatch (F4 L1b)**: `DownloadFileTool` declares `Requires = (FilesystemConfig,)`; consumes `self._cross_configs[FilesystemConfig]` in `execute`.
- **F5 leg-design Open Question**: "`download_file` content-type filter — refuse certain content types (e.g., `application/x-executable`)? Probably not — `download_file` is operator-trusted via path-scope." **Resolved here**: NO content-type filter. The path-scope check is the security boundary (operator decides where files can land); content-type filtering would be a different policy concern, deferred to a future flight if needed.
- **Streaming abort pattern** (architect-noted in F5 spec L4 leg): use nested `async with client.stream(...) as resp:` then `async for chunk in resp.aiter_bytes(): ... if exceeded: raise ConstraintError ...; unlink in finally`.
- **`response_size_cap_bytes` is the on-disk cap for `download_file`** (NOT in-memory) per the F5 architect Q&A.

## Inputs

- `the_one/tools/_web_config.py` — `WebConfig`, `_url_check`, `SSRFGuardedTransport`.
- `the_one/tools/filesystem.py` — `FilesystemConfig`, `_filesystem_check`, `CheckMode` (post-L0).
- `the_one/tools/web.py` — `HttpRequestTool`, `FetchUrlTool` (post-L2/L3 reference for envelope/transport-seam).
- `the_one/tools/builtins.py::_TOOL_CLASSES` — 18 entries (post-L3); post-L4 = 19.

## Outputs

- `the_one/tools/web.py`:
  - **`DownloadFileTool(Tool)`** appended after `FetchUrlTool`.
  - `name = "download_file"`.
  - `description = "Download a URL's content to a file. Path may be absolute or relative; relative paths resolve against the agent server's CWD. Refused if path is outside the operator-set path allowlist. Streams the response and aborts (removing the partial file) if the size cap is exceeded mid-stream. Same SSRF + URL allowlist + timeout cap as http_request. Use this for binary content (PDFs, images, archives); use fetch_url for HTML/text."`.
  - `parameters = {"type": "object", "properties": {"url": {"type": "string", "description": "URL to download."}, "path": {"type": "string", "description": "Where to write the file. Refused if outside path allowlist."}}, "required": ["url", "path"]}`.
  - `Config = WebConfig`.
  - `Requires = (FilesystemConfig,)`.
  - `_build_transport(self, cfg)`: same shape as L2/L3.
  - `execute(self, url, path, **kwargs) -> str`:
    1. `cfg: WebConfig = self._config`; `fs_cfg: FilesystemConfig = self._cross_configs[FilesystemConfig]`.
    2. `clipped = cfg.timeout_seconds_default` (no agent-passed timeout — keep param surface tiny).
    3. Four-clause envelope:
       - `try`:
         - `_url_check(url, cfg)`.
         - `target = _filesystem_check(path, fs_cfg, mode=CheckMode.WRITE_EXISTING_PARENT)` — canonicalizes; refuses out-of-scope paths.
         - Build SSRF-guarded client (same shape as L2/L3).
         - **Streaming download with mid-stream abort**:
           ```python
           total_bytes = 0
           cap = cfg.response_size_cap_bytes
           # Parent must pre-exist (CheckMode.WRITE_EXISTING_PARENT validated
           # this above); do NOT auto-mkdir — agent has the `mkdir` tool.
           try:
               with target.open("wb") as fh:
                   async with client.stream("GET", url) as resp:
                       async for chunk in resp.aiter_bytes():
                           if total_bytes + len(chunk) > cap:
                               raise ConstraintError(
                                   f"response exceeded {cap} bytes; partial file removed"
                               )
                           fh.write(chunk)
                           total_bytes += len(chunk)
                       status = resp.status_code
           except ConstraintError:
               target.unlink(missing_ok=True)
               raise
           return f"[{status}] downloaded {total_bytes} bytes to {target}"
           ```
       - `except ConstraintError as e: return f"[error] [constraint] {e}"`
       - `except (asyncio.TimeoutError, httpx.TimeoutException): return f"[error] Download timed out after {clipped}s"` (F5 wording — distinct from L2 "Request" / L3 "Fetch").
       - `except httpx.TooManyRedirects: return f"[error] [constraint] exceeded redirect cap of {cfg.redirect_cap}"`.
       - `except Exception as e:`:
         - Try `target.unlink(missing_ok=True)` if `target` was set (partial cleanup on unexpected errors). Wrap in `try/except` to avoid masking the original error.
         - Return `f"[error] {e}"`.
- `the_one/tools/builtins.py`:
  - Import `DownloadFileTool`.
  - Add to `_TOOL_CLASSES` (insert after `fetch_url`, before `web_search`):
    ```python
    "download_file": DownloadFileTool,
    ```
  - Total: 19 entries post-L4.
- `the_one/interfaces/web/static/js/areas/studio.js`:
  - Update `TOOL_CATEGORIES['Web']` to include `"download_file"` (alphabetical: `['download_file', 'fetch_url', 'http_request', 'web_search']`).
- `tests/test_web_tools.py`:
  - **New `TestDownloadFileTool` class** with these tests:
    - `test_construction_shape`: builds; `Config is WebConfig`; `Requires == (FilesystemConfig,)`.
    - `test_happy_path`: in-scope path, mock returns 1KB body; tool writes file; returns `[200] downloaded 1024 bytes to /path`. Verify file content.
    - `test_path_outside_allowlist_refused`: `fs_cfg=FilesystemConfig(path_allowlist=[str(tmp_path)])`; agent passes `path="/etc/passwd"`; tool returns `[error] [constraint] path '/etc' outside allowlist` (or similar L0 wording). File not created.
    - `test_mid_stream_size_cap_aborts`: `cfg.response_size_cap_bytes=1024`; mock returns chunks totaling 5KB; tool aborts mid-stream, unlinks partial file, returns `[error] [constraint] response exceeded 1024 bytes; partial file removed`. Verify file does NOT exist post-call.
    - `test_url_check_refused`: agent passes `ftp://...` → `[error] [constraint] scheme 'ftp' refused`. No file created.
    - `test_redirect_cap_exceeded`: `cfg.redirect_cap=1`; mock chain emits 302 → 302; tool returns `[error] [constraint] exceeded redirect cap of 1`. No partial file.
    - `test_timeout_via_httpx_readtimeout`: mock raises `httpx.ReadTimeout`; tool returns `[error] Download timed out after Ns`. No file (or partial file unlinked).
    - `test_relative_path_resolves_against_cwd`: agent passes `path="downloads/file.bin"`; tool resolves against the FastAPI process's CWD (which inside the container is `/app`). The test must construct `FilesystemConfig(path_allowlist=["/app"])` so the resolved path is in scope.
    - `test_partial_file_cleaned_on_unexpected_error`: mock raises a generic `RuntimeError` mid-stream (not a ConstraintError); tool catches via the generic `except Exception` clause, unlinks the partial file, returns `[error] {RuntimeError msg}`. Verify file does NOT exist.
- `tests/test_builtins.py`:
  - Update count assertions (18 → 19) at all 3 sites + comment references.
  - Add `"download_file"` to the tool-name set.

## Acceptance Criteria

- [x] `the_one/tools/web.py::DownloadFileTool` exists with `Config = WebConfig`, `Requires = (FilesystemConfig,)`.
- [x] `description` mentions path-scope, mid-stream abort, SSRF/URL/timeout constraints, and the use-binary-not-fetch-url disambiguation. Small-model-readable.
- [x] `parameters` requires both `url` and `path`.
- [x] Path validation via `_filesystem_check(path, fs_cfg, mode=CheckMode.WRITE_EXISTING_PARENT)` — uses the L0-unified helper.
- [x] Streaming download via `httpx.AsyncClient.stream()` — NOT loading the whole body into memory.
- [x] **Mid-stream size-cap abort**: tracks `total_bytes` per chunk; raises `ConstraintError` when `total_bytes + len(chunk) > cap` BEFORE writing the offending chunk; unlinks partial file in `finally`-equivalent block.
- [x] **Partial-file cleanup also on unexpected errors**: the generic `except Exception` clause attempts `target.unlink(missing_ok=True)` before returning `[error] {e}`.
- [x] Four-clause envelope (`ConstraintError → (asyncio.TimeoutError, httpx.TimeoutException) → httpx.TooManyRedirects → Exception`).
- [x] Timeout-error wording: `[error] Download timed out after Ns` (distinct from L2/L3).
- [x] `_build_transport(cfg)` helper for test-seam consistency.
- [x] Registered in `_TOOL_CLASSES` (19 entries) and Studio `TOOL_CATEGORIES['Web']`.
- [x] All 9 new tests pass.
- [x] Full unit suite green (modulo CSS-token red).
- [x] `ruff check` clean on touched files.

## Verification Steps

```bash
docker exec the-one python -c "
from the_one.tools.web import DownloadFileTool
from the_one.tools._web_config import WebConfig
from the_one.tools.filesystem import FilesystemConfig
t = DownloadFileTool(WebConfig(), cross_configs={FilesystemConfig: FilesystemConfig()})
assert t.Config is WebConfig
assert t.Requires == (FilesystemConfig,)
print('OK construction')
"

docker exec the-one python -c "
from the_one.tools.builtins import _TOOL_CLASSES
assert len(_TOOL_CLASSES) == 19, len(_TOOL_CLASSES)
assert 'download_file' in _TOOL_CLASSES
print('OK 19 tools')
"

# End-to-end happy path via mocked transport
docker exec the-one python -c "
import asyncio
import tempfile
from pathlib import Path
import httpx
from the_one.tools.web import DownloadFileTool
from the_one.tools._web_config import WebConfig
from the_one.tools.filesystem import FilesystemConfig
async def main():
    def handler(request):
        return httpx.Response(200, content=b'hello, world!\n')
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        target = td_path / 'out.txt'
        t = DownloadFileTool(
            WebConfig(),
            cross_configs={FilesystemConfig: FilesystemConfig(path_allowlist=[td])},
        )
        t._build_transport = lambda cfg: httpx.MockTransport(handler)
        out = await t.execute(url='http://example.com', path=str(target))
        assert '[200]' in out and 'downloaded' in out, out
        assert target.read_bytes() == b'hello, world!\n', target.read_bytes()
        print('OK happy path')
asyncio.run(main())
"

docker exec the-one pytest tests/test_web_tools.py tests/test_builtins.py -x -q
docker exec the-one pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined
docker exec the-one ruff check the_one/tools/web.py the_one/tools/builtins.py tests/test_web_tools.py tests/test_builtins.py
```

## Implementation Guidance

1. **Append `DownloadFileTool` to `the_one/tools/web.py`** following L3's `FetchUrlTool` pattern. Add `Requires = (FilesystemConfig,)` class attribute and consume `self._cross_configs[FilesystemConfig]` in `execute`.

2. **Streaming + cleanup pattern**:
   ```python
   target = _filesystem_check(path, fs_cfg, mode=CheckMode.WRITE_EXISTING_PARENT)
   transport = self._build_transport(cfg)
   total_bytes = 0
   cap = cfg.response_size_cap_bytes
   if cfg.redirect_cap == 0:
       follow = False
       max_redirs = 0
   else:
       follow = True
       max_redirs = cfg.redirect_cap

   # NB: do NOT auto-mkdir parents — `WRITE_EXISTING_PARENT` requires
   # the parent to pre-exist (consistent with F3 move_file destination
   # and the mission's "agent has an explicit mkdir tool" stance).
   status: int | None = None

   try:
       with target.open("wb") as fh:
           async with httpx.AsyncClient(
               transport=transport,
               timeout=clipped,
               follow_redirects=follow,
               max_redirects=max_redirs,
           ) as client:
               async with client.stream("GET", url) as resp:
                   status = resp.status_code
                   async for chunk in resp.aiter_bytes():
                       if total_bytes + len(chunk) > cap:
                           raise ConstraintError(
                               f"response exceeded {cap} bytes; partial file removed"
                           )
                       fh.write(chunk)
                       total_bytes += len(chunk)
       return f"[{status}] downloaded {total_bytes} bytes to {target}"
   except ConstraintError:
       target.unlink(missing_ok=True)
       raise
   ```

3. **Generic-exception cleanup**: in the `except Exception` clause, attempt cleanup defensively:
   ```python
   except Exception as e:
       try:
           target.unlink(missing_ok=True)
       except (NameError, OSError):
           # `target` may not be defined if the error fired before _filesystem_check;
           # OSError is fine to swallow during cleanup.
           pass
       return f"[error] {e}"
   ```
   Actually `NameError` won't fire — `target` is set in the try block, but if an exception fires before `_filesystem_check` (e.g., `_url_check` raises ConstraintError), `target` is undefined. The `ConstraintError` clause catches that path FIRST, so by the time the generic `Exception` clause fires, `target` is set. But defensive — test by intentionally raising before _filesystem_check.

4. **Test fixture**: use `tmp_path` (pytest fixture) for the path-allowlist directory and target paths. The L0-unified `_filesystem_check(mode=WRITE_NEW)` accepts non-existent target paths — agents specify a path that doesn't exist yet.

5. **Studio `TOOL_CATEGORIES['Web']` ordering**: insert `"download_file"` (alphabetical position).

6. **`test_relative_path_resolves_against_cwd`**: the FastAPI process's CWD inside the container is `/app`. Test constructs `FilesystemConfig(path_allowlist=["/app"])` so a relative path like `"downloads/file.bin"` resolves to `/app/downloads/file.bin` and is in scope. Use `tmp_path` if `/app` is read-only — actually `/app` is bind-mounted, so writing to subdirs there might leak files into the host's `the_one/`. **Better**: skip this test or use a `monkeypatch.chdir(tmp_path)` to control the process CWD.

## Edge Cases

- **Parent must pre-exist** — `download_file` uses `CheckMode.WRITE_EXISTING_PARENT`. The agent has an explicit `mkdir` tool; auto-creating parents would diverge from F3's `move_file` semantic. If the parent is missing, `_filesystem_check` raises `FileNotFoundError`, caught by the generic `except Exception` clause → agent gets `[error] parent does not exist for path '...'` and can `mkdir` first.

- **Final `status` value when stream succeeds but body is empty**: `total_bytes=0`, `status` is set in the `async with client.stream(...)` block. Return `[200] downloaded 0 bytes to /path`. Acceptable.

- **`_filesystem_check(mode=WRITE_EXISTING_PARENT)` raises `FileNotFoundError`** if parent doesn't exist (per L0 contract). The four-clause envelope's generic `except Exception` catches this and returns `[error] parent does not exist for path '...': ...`. Agent gets a clean error and can `mkdir` the parent.

- **Resumable downloads / range requests**: out of scope for F5. Agent gets an "all or nothing" download.

## Files Affected

- `the_one/tools/web.py` — append `DownloadFileTool`.
- `the_one/tools/builtins.py` — register in `_TOOL_CLASSES` (18 → 19).
- `the_one/interfaces/web/static/js/areas/studio.js` — add `"download_file"` to `TOOL_CATEGORIES['Web']`.
- `tests/test_web_tools.py` — new `TestDownloadFileTool` class with 9 tests.
- `tests/test_builtins.py` — update count assertions (18 → 19) and tool-name set.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
