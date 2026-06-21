# Leg: web-tool-stream-and-cap

**Status**: completed
**Flight**: [Chat-loop Robustness & Control](../flight.md)

## Objective
Make `http_request` and `fetch_url` incapable of hanging on a continuous-stream URL
by streaming the body with an in-loop byte cap (mirroring `download_file`), a total
wall-clock deadline, and a media content-type short-circuit.

## Context
- Flight DD1. Root cause (live repro this session): both tools do
  `await client.request()/get()` which buffers the **entire** body before returning;
  a continuous audio stream (e.g. `https://stream.radioparadise.com/aac-320`) never
  completes the body → infinite hang. httpx's `timeout` is per-operation (read =
  between-bytes gap), not a total deadline, so a continuously-sending stream never
  trips it; the byte cap is applied post-read so it never fires.
- `download_file` (web.py:288-304) ALREADY uses the correct pattern — reuse it.
- Design-review corrections: headers are available from `client.stream` before the
  first `aiter_bytes` pull; reuse `_is_binary_content_type` for the short-circuit;
  the HTML path needs **accumulate+decode** (no `resp.text` after a streamed read →
  `StreamConsumed`) and **head-preserving** truncation (tail-truncated HTML breaks
  `readability.Document`).

## Inputs
- `the_one/tools/web.py` with `http_request` (HttpRequestTool, ~:87-139),
  `fetch_url` (FetchUrlTool, ~:169-220), `download_file` (DownloadFileTool,
  ~:288-304) as the streaming precedent.
- `the_one/tools/_web_config.py`: `response_size_cap_bytes` (1_048_576),
  `timeout_seconds_default` (30), `timeout_seconds_max` (120),
  `_is_binary_content_type` (~:88-102), `_truncate_response` (tail-preserving).
- `tests/test_web_tools.py` (existing tool tests; `download_file` cap test uses a
  finite body — a never-ending fixture is NEW).

## Outputs
- `http_request` and `fetch_url` stream the body and cannot hang on an endless
  stream.
- New unit tests incl. a never-ending iterator-backed `MockTransport`.

## Acceptance Criteria
- [ ] `http_request` and `fetch_url` read the body via `async with client.stream(...)`
      + `async for chunk in resp.aiter_bytes()`, enforcing `response_size_cap_bytes`
      **during** iteration (abort/ConstraintError once exceeded), like `download_file`.
- [ ] Both wrap the whole `client.stream` block in a total deadline
      (`asyncio.wait_for`, ceiling = `timeout_seconds_max`); on timeout they return
      the existing `[error] ... timed out` string (no hang).
- [ ] Both short-circuit BEFORE pulling the body when the response `Content-Type` is
      `audio/*`, `video/*`, or `application/octet-stream` (via `_is_binary_content_type`),
      returning a clear "looks like a media stream, not fetchable as text" message.
- [ ] `fetch_url`'s HTML path accumulates capped bytes + decodes (no `resp.text`
      post-stream) and head-preserves before `readability.Document`; a large HTML page
      still extracts sensible markdown.
- [ ] A never-ending stream fixture (iterator-backed `MockTransport`) proves both
      tools **cap-abort** rather than hang.
- [ ] No regression: existing `tests/test_web_tools.py` passes; normal HTML/JSON/text
      fetches behave as before.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_web_tools.py -x --timeout 30`
- New test: endless-iterator transport → `http_request`/`fetch_url` return a
  constraint/cap error within the cap, not a timeout-after-N and not a hang.
- New test: a `Content-Type: audio/aac` response → media short-circuit, body never pulled.
- Regression: an HTML fixture > cap → still extracts (head-preserved), not garbage.

## Implementation Guidance
1. **Refactor `HttpRequestTool.execute`** (web.py:104-131): replace
   `resp = await client.request(...)` + post-read truncate with
   `async with client.stream(method, url, ...) as resp:` — check
   `resp.headers.get("content-type")` via `_is_binary_content_type` → short-circuit;
   else accumulate `aiter_bytes()` into a `bytearray`, breaking/raising at the cap;
   decode + return. Wrap the whole block in `asyncio.wait_for(..., clipped)` (or rely
   on a total deadline helper) so a trickle stream can't outlast the deadline.
2. **Refactor `FetchUrlTool.execute`** (web.py:169-212): same streaming + cap +
   short-circuit; for `text/html`, build the decoded string from the accumulated
   (head-preserved) bytes, then `Document(...)` + `markdownify` as today.
3. **Shared helper**: factor the stream-read-with-cap into a small helper reused by
   all three tools if clean; otherwise mirror `download_file` inline.
4. **Tests**: add an iterator/generator-backed `httpx.MockTransport` that yields
   bytes indefinitely; assert cap-abort. Add the media short-circuit test and the
   large-HTML head-preserve test.

## Edge Cases
- **Trickle stream under the cap**: total deadline (`asyncio.wait_for`) bounds it.
- **`client.stream` + `wait_for` cancellation**: the `async with` `__aexit__` closes
  the connection on cancel — confirm no leaked connection.
- **HTML smaller than cap**: unchanged behavior (full extraction).
- **Redirect cap / constraint errors**: preserve existing `[error] [constraint]` paths.

## Files Affected
- `the_one/tools/web.py` — refactor `http_request` + `fetch_url` (and optional shared
  stream-read helper).
- `tests/test_web_tools.py` — never-ending fixture, media short-circuit, large-HTML.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:** (deferred-commit flight —
do NOT commit per leg)
- [ ] All acceptance criteria verified
- [ ] Tests passing (`tests/test_web_tools.py`)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (commit deferred to flight-wide review)

---

## Design-Review Corrections (binding)
- **Media short-circuit must NOT reference body length**: after switching to
  `client.stream`, `resp.content` raises `StreamConsumed`. The short-circuit message
  reports the `Content-Type` only (e.g. `[error] looks like a media stream
  (type={bare}), not fetchable as text`). Do not redirect to `download_file` for an
  infinite stream.
- **Use a NARROW stream predicate, not `_is_binary_content_type`**: that helper
  (`_web_config.py:340`) also matches image/pdf/zip/wasm/etc. Reusing it would
  regress `http_request`'s current binary tail-truncation (`<binary content>` path).
  Add a small dedicated check for `audio/*` | `video/*` | `application/octet-stream`
  only; leave existing binary handling intact for other types.
- **HTML head-preserve AC made verifiable**: the large-HTML test asserts a specific
  known substring from the HEAD of the fixture page is present in the extracted
  markdown (not a subjective "sensible").
- **Fixture**: confirm the installed httpx supports a never-ending async byte
  iterator via `MockTransport` `Response(stream=...)` before locking the test.
