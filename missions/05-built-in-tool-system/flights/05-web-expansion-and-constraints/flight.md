# Flight: Web Expansion & Constraints

**Status**: completed
**Mission**: [Built-In Tool System](../../mission.md)

## Contributing to Criteria

- [ ] Web tooling supports raw HTTP, reader-mode page retrieval, file download, and pluggable search; requests targeting internal-network, loopback, or cloud-metadata addresses are blocked by default with a clear opt-out path for advanced operators *(F5 ships the full surface)*
- [ ] Each tool category enforces tool-level constraints — path scope, read-size caps, output caps, timeout caps, URL/host scope — that apply to all agents by default, and per-agent overrides can only narrow those constraint values, never widen them *(F5 introduces URL/host scope + redirect cap + response-size cap for web)*
- [ ] Each kept tool has automated coverage proving it behaves correctly under happy-path use and under constraint-violation use (path-scope rejections, size-cap truncation, timeout caps, SSRF blocks, binary-file refusals) *(F5 covers web subset including SSRF + DNS-rebind)*

---

## Pre-Flight

### Objective

Land the full web-tool surface and the third constraint enforcement on F2's resolver seam beyond filesystem and execution. Add `fetch_url` (readability-extracted markdown of the main content of a page) and `download_file` (writes through `FilesystemConfig` path scope). Migrate `http_request` and `web_search` to a per-category `WebConfig` (response-size cap, redirect cap, timeout caps, URL/host allowlist + denylist). Introduce **SSRF protection on by default** via resolve-then-pin: resolve the URL's hostname through `ipaddress`-stdlib checks, refuse loopback / RFC1918 / link-local / cloud-metadata addresses, and pass the **resolved IP** (not the hostname) to httpx via a custom `HTTPTransport` to defeat DNS-rebinding TOCTOU. Land a one-method `SearchBackend` protocol with a single concrete `DDGSearchBackend` (fixing the F1 known-issue DDG breakage — root cause is a missing browser User-Agent header against DDG's anti-bot interstitial, verified against `https://html.duckduckgo.com/html/` returning `result__a` markers when a browser-like UA is sent).

L0 lands the F4-deferred `_filesystem_check_*` helper unification (per F4 Decision 8, Decision-revision deferred to "post-F4 maintenance"; folded into F5 because `download_file` adds a 7th call site to the family).

Includes a guided HAT leg validating that the agent recovers gracefully from every new constraint type — including a SSRF DNS-rebind scenario — and that the WebSocket UI surface (post-F4 fixes) handles slow `download_file` operations cleanly across switch-and-rejoin flows.

### Open Questions

- [x] **Readability library choice** — `readability-lxml` (extraction) + `markdownify` (HTML→markdown). Mature; two deps but each is single-purpose. `trafilatura` was considered but adds more aggressive cleaning that may strip content we want to keep. *(see Decision 1)*
- [x] **`SearchBackend` extensibility shape** — land the protocol now (one method, one concrete impl); `DDGSearchBackend` is the only F5 backend. F6 admin "test button" needs a uniform interface. F1 known-issue close ships in the same leg. *(see Decision 2)*
- [x] **F4-deferred filesystem helper unification** — folded into F5 as L0 (pre-implementation maintenance leg). `download_file` adds a 7th call site to `_filesystem_check_*` family. *(see Decision 3)*
- [x] **`HttpRequestTool` migration vs split** — keep one tool. SSRF + URL/host allowlist + caps apply uniformly. *(see Decision 4)*
- [x] **`download_file` path semantics** — absolute or relative; relative resolves through `_filesystem_check(mode=WRITE_NEW)` against process cwd. *(see Decision 5)*
- [x] **SSRF transport mechanism** — custom `httpx.AsyncHTTPTransport` subclass with `request.extensions["sni_hostname"]` for SNI preservation + URL host rewrite to resolved IP. Verified against httpx 0.27+ and httpcore 1.x. *(see Decision 6)*
- [x] **SSRF allowlist shape** — `extra_allowed_hosts: Annotated[list[str], Narrow]` (corrected from initial `NarrowSuperset` per architect review — `Narrow` enforces agent-set ⊆ operator-set, the right semantic for an allowlist). *(see Decision 7)*
- [x] **`fetch_url` parameter shape** — single required `url` parameter; readability for HTML, raw body for text/JSON, refuse-with-guidance for binary. *(see Decision 8)*
- [x] **Redirect cap is tool-level only** — `redirect_cap` Field-only (no marker); resolver raises `ValueError` at agent-build time on agent override (verified against `the_one/tools/resolver.py:244-248`). *(see Decision 9)*
- [x] **Response-size cap behavior** — tail-preserving truncation; new helper `_truncate_response` (NOT reusing `_truncate_output` due to different boundary semantics — single-stream, content-typed). *(see Decision 10)*
- [x] **HAT inclusion** — yes. 9 operator-driven scenarios; DNS-rebind moved to L1 unit test (cannot be exercised operator-driven). *(see Decision 11)*
- [x] **`SearchBackend` lifecycle** — option (a): backends in a `_search_backends` dict alongside `cross_configs`, parallel-shape; passed via `cross_configs[SearchBackend]` injection. Per-`get_tools()` lifecycle. *(see Decision 12)*
- [ ] **`fetch_url` content-type handling** — readability only on `Content-Type: text/html`; raw decoded body for text/JSON; refuse-with-guidance for binary. Resolved at L3 leg-design time.
- [ ] **`download_file` content-type filter** — probably not (operator-trusted via path-scope). Resolved at L4 leg-design time.

### Design Decisions

**Decision 1 — `readability-lxml` + `markdownify` for `fetch_url` extraction**:

```python
# pyproject.toml dependencies (add):
"readability-lxml>=0.8",
"markdownify>=0.13",
```

- `readability-lxml` extracts the main article content from HTML (Mozilla's Readability port).
- `markdownify` converts the extracted HTML to markdown.
- Both are mature, single-purpose, and have been on PyPI for ~10 years.
- Trade-off considered: `trafilatura` (one dep, but more aggressive cleaning). Rejected — readability+markdownify gives us more control over the HTML→markdown step (e.g., preserving links).
- Forward-reference: F6's "test button" for `fetch_url` exercises the readability+markdownify pipeline against a fixture URL.

**Decision 2 — `SearchBackend` protocol with `DDGSearchBackend` only**:

```python
# the_one/tools/_search_backends.py (NEW)
@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str

class SearchBackend(Protocol):
    name: str  # "duckduckgo", "brave", etc.
    async def search(
        self, query: str, max_results: int
    ) -> list[SearchResult]: ...

class DDGSearchBackend:
    name = "duckduckgo"

    def __init__(self, http_client: httpx.AsyncClient):
        self._client = http_client

    async def search(self, query, max_results):
        # POST https://html.duckduckgo.com/html/ with browser UA
        # Parse result__a + result__snippet markers
        ...
```

- The F1 known issue (no DDG results) closes here — root cause is missing User-Agent. Verified against the live DDG endpoint that a browser UA returns 200 + 10 result markers.
- Backend instances live in a registry (similar to LLM providers); F6 admin will let operators pick the active backend per-agent or per-tool-config.
- Single implementation in F5 keeps the surface small. Brave Search / Tavily / Google CSE can land in a future flight without touching `WebSearchTool`.

**Decision 3 — Filesystem helper unification as L0**:

The F3 family — `_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path` — has three call patterns:
- read (path must exist + be in scope)
- write to existing file (path must exist or parent in scope)
- write to non-existent file (parent must exist + path in scope)

F4's `_cwd_check` added a 4th pattern (path must be a directory + in scope). F5's `download_file` adds a 5th: write a fresh file path that may or may not exist, parent must be in scope.

L0 unifies these into a single dispatched helper:

```python
# the_one/tools/filesystem.py (refactor in L0)
class CheckMode(Enum):
    READ = "read"               # must exist; in scope
    WRITE_NEW = "write_new"     # parent in scope; path may not exist
    WRITE_EXISTING = "write_existing"  # path in scope, parent OR path exists
    DIRECTORY = "directory"     # in scope; is a directory

def _filesystem_check(
    path: str | Path,
    cfg: FilesystemConfig,
    mode: CheckMode = CheckMode.READ,
) -> Path: ...
```

- Existing call sites (`_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path`, `_cwd_check`) remain as thin shims that call into the dispatched helper. Backward compat for anything outside `the_one/tools/`. F4's `_cwd_check` re-uses `mode=DIRECTORY`.
- Trade-off: 4-mode dispatch is slightly less obvious than 4 distinct functions. Counter: each mode shares ~80% of the canonicalize-then-allowlist-then-denylist flow. Unification eliminates ~50 LoC of near-duplication and gives F5 a single shape to consume.
- Test suite: F3's tests (`test_filesystem_helpers.py`) are the regression net — must pass unchanged.

**Decision 4 — Single `HttpRequestTool` (no split)**:

`HttpRequestTool` post-F5 enforces:
- SSRF (resolve-then-pin, blocks loopback / RFC1918 / link-local / cloud-metadata)
- URL/host allowlist + denylist
- Response-size cap (tail-preserving)
- Redirect cap (tool-level only)
- Timeout caps (Narrow + cross-field validator)

Operators who need to reach internal infrastructure (Ollama, internal HTTP APIs) curate `extra_allowed_hosts`. There is no "raw HTTP" tool that bypasses constraints — the agent can't get a pre-F5-equivalent surface back even if the operator wants. This is intentional per the mission's "SSRF protection is on by default" framing.

**Decision 5 — `download_file` path semantics**:

```python
async def execute(
    self,
    url: str,
    path: str,           # required — explicit path argument
    **kwargs: Any,
) -> str: ...
```

- `path` may be absolute or relative; relative resolves against the FastAPI process's cwd via `_filesystem_check(mode=WRITE_NEW)`.
- Refused if outside `FilesystemConfig.path_allowlist`.
- Parent directory must exist (no auto-`mkdir`; agents have a `mkdir` tool for that).
- Response-size cap applies during streaming — partial-download handling: refuse and remove the partial file if the cap is exceeded mid-stream.

**Decision 6 — Custom `httpx.AsyncHTTPTransport` for SSRF resolve-then-pin**:

```python
# the_one/tools/_web_transport.py (NEW)
class SSRFGuardedTransport(httpx.AsyncHTTPTransport):
    """Resolves the URL's hostname BEFORE connecting; refuses requests
    whose resolved IPs hit any blocked range; passes the resolved IP
    (not the hostname) to the underlying transport so DNS rebinding
    cannot return a different address between policy-check and connect.

    The Host: header is preserved for SNI and virtual-hosting reasons
    by setting the request URL's host to the resolved IP and adding/
    overriding the Host header to the original hostname.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        original_host = request.url.host
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        loop = asyncio.get_running_loop()
        resolved_ips = await loop.getaddrinfo(
            original_host, port, type=socket.SOCK_STREAM,
        )
        # Filter to first IP that passes the SSRF check
        for family, _type, _proto, _canonname, sockaddr in resolved_ips:
            ip = sockaddr[0]
            if not _is_ssrf_blocked(ip, allowed_extra=self._extra_allowed):
                # Replace URL host with resolved IP for the connect target,
                # AND preserve SNI + cert-name validation by stashing the
                # original hostname on `request.extensions["sni_hostname"]`
                # — httpcore reads this and passes it as TLS server_hostname.
                # Setting only the Host: header is INSUFFICIENT for cert
                # validation; SNI dispatch uses extensions, not headers.
                request.extensions = {
                    **request.extensions,
                    "sni_hostname": original_host,
                }
                request.headers["Host"] = original_host  # HTTP/1.1 vhost routing
                request.url = request.url.copy_with(host=ip)
                return await super().handle_async_request(request)
        raise SSRFBlockedError(
            f"all resolved IPs for {original_host} are blocked: "
            f"{[s[4][0] for s in resolved_ips]}"
        )
```

- `_is_ssrf_blocked(ip, allowed_extra)` uses `ipaddress.ip_address(ip)` then checks: `is_loopback`, `is_link_local`, `is_private` (covers RFC1918), explicit cloud-metadata IP equality (`169.254.169.254`, `fd00:ec2::254`), and the `allowed_extra` host:port list as the override.
- The transport is constructed **per-tool-instance** (in `__init__`) and reused across calls. Per the session-bound freshness contract (`agents.md:187`), `extra_allowed_hosts` cannot change mid-session, so per-instance construction is safe and cheaper than per-call.
- Test pattern: monkeypatch `socket.getaddrinfo` (or pass a fixture-provided resolver) to return controlled IPs. **DNS-rebind validation is a unit test**, not a HAT scenario — the rebind requires Python-process-level monkeypatching that operator-driven HAT cannot exercise. Unit test: first call returns public IP, second call returns 127.0.0.1; assert second call is blocked even after the first passed.
- HTTPS certificate validation is preserved via `request.extensions["sni_hostname"]` — httpcore reads this and passes it as the TLS `server_hostname`. The server presents a cert valid for the original name (not the IP), and validation succeeds. **Setting only the `Host:` header is insufficient** — SNI dispatch goes through extensions, not headers; this distinction is the architect's high-severity correction to the original spec.
- `loop.getaddrinfo` is the async wrapper around the (synchronous) `socket.getaddrinfo`; using `asyncio.get_running_loop()` (not `get_event_loop()`, which is deprecation-warned when no loop is running) is the correct shape inside the async transport's `handle_async_request`.

**Decision 7 — `extra_allowed_hosts` allowlist shape**:

```python
# WebConfig field — Narrow (NOT NarrowSuperset).
# Resolver's Narrow on list[T] does subset (agent_val ⊆ tool_val):
# every agent entry must be in the tool's value. Matches the semantic
# we want: operator broadens the SSRF block list; agent can only stay
# within or narrow that broadening.
extra_allowed_hosts: Annotated[list[str], Narrow] = Field(
    default_factory=list,
    description=(
        "Hosts whose resolved IPs are exempt from the SSRF default-block "
        "list. Each entry: 'hostname' (any port) or 'hostname:port'. "
        "Common operator additions: 'localhost:11434' (Ollama), "
        "internal LAN HTTP services. The protection itself is not "
        "disable-able; this list is the only opt-out."
    ),
)
```

- **`Narrow` is the right marker** (not `NarrowSuperset`): the resolver's `Narrow`-on-`list` checks `every(agent_entry in tool_value)` (subset) — exactly the "agent ⊆ operator" semantic we want for an allowlist where operator is broader and agent is narrower. `NarrowSuperset` is the inverse and applies to denylist-style fields where operator-baseline must be preserved (every operator entry must remain).

**Decision 8 — `fetch_url` parameter shape**:

```python
{
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "URL to fetch and extract main content."},
    },
    "required": ["url"],
}
```

- Always runs readability extraction → markdown when `Content-Type: text/html`.
- For non-HTML content types (text/plain, application/json, etc.), returns the decoded body up to the response-size cap (no readability).
- For binary content types (application/pdf, image/*, application/octet-stream), refuses with a guidance message: "use `download_file` for binary downloads."
- Description: "Fetch a URL and extract the main article content as markdown. For HTML pages, runs readability extraction to strip navigation/ads/sidebars. For text/JSON, returns the body. For binary content, use `download_file` instead."

**Decision 9 — Redirect cap is tool-level only**:

```python
# WebConfig field — no Narrow/Substitute marker, so agent overrides on
# this key are rejected by the resolver at AgentFactory.create() time.
redirect_cap: int = Field(
    5,
    ge=0,
    le=20,
    description=(
        "Maximum HTTP redirects per request. Tool-level only — agents "
        "cannot narrow this (per mission constraint). Set 0 to follow "
        "no redirects (httpx returns the 3xx body verbatim, since "
        "follow_redirects=False semantics apply)."
    ),
)
```

- Per the mission's "redirect cap (default 5, tool-level only)".
- **Resolver behavior verified** against `the_one/tools/resolver.py:244-248`: when an agent override sets a key whose schema field has NO marker, the resolver raises `ValueError("field {schema}.{key} has no Narrow/Substitute marker; declare one of (Narrow, NarrowPrefix, NarrowSuperset, Substitute)")`. So agents trying to override `redirect_cap` get a clean error at `AgentFactory.create()` time — surfaced as a startup error, NOT a per-call error.
- L1 must add a regression test asserting (a) the exact `ValueError` message and (b) that the failure surfaces at agent-build time rather than tool-execution time.
- **Redirect=0 semantics**: when `redirect_cap=0`, the httpx client uses `follow_redirects=False` so it returns the 3xx body verbatim (most agent-friendly: agent sees the redirect target and can decide). When `redirect_cap >= 1`, `follow_redirects=True, max_redirects=redirect_cap` raises `httpx.TooManyRedirects` if exceeded.

**Decision 10 — `_truncate_response` helper for response-size cap**:

```python
# the_one/tools/web.py (helper)
def _truncate_response(
    body: bytes,
    cfg: WebConfig,
    *,
    content_type: str | None = None,
) -> tuple[str, bool]: ...
```

- Tail-preserving like F4's `_truncate_output` (drop FRONT, keep tail).
- Marker: `[... truncated N bytes; showing last M bytes of response ...]\n`.
- Distinct from `_truncate_output` because:
  - No stdout/stderr split (single response stream).
  - No exit code suffix.
  - Decoding may use the response's `Content-Type: charset=...` instead of fallback `errors="replace"`.
- For binary content types, returns `(b"<binary content; N bytes>", was_truncated=True)`.

**Decision 11 — HAT scope (9 operator-driven scenarios; DNS-rebind moved to L1 unit test)**:

DNS-rebind cannot be exercised operator-driven (requires Python-process-level `monkeypatch.setattr(socket, "getaddrinfo", ...)`). It lands in L1's unit-test set instead, where the test pattern is straightforward: first resolution returns a public IP and passes; second resolution returns `127.0.0.1` and is blocked even though the first call was allowed.

HAT scenarios (operator-driven via `POST /api/chat`):
1. `http_request` to a public URL — happy path, response-size cap not exceeded.
2. `http_request` exceeding response-size cap — tail-preserved with marker.
3. SSRF block: `http_request` to `http://169.254.169.254/` (cloud metadata) → `[error] [constraint] ...`.
4. SSRF block: `http_request` to `http://10.0.0.1/` (RFC1918) → `[error] [constraint] ...`.
5. SSRF allowlist (operator-broadened): `extra_allowed_hosts=["localhost:8484"]` — agent fetches the dev container's own `/api/info` and reports.
6. SSRF allowlist (agent-narrowed): same operator allowlist, but agent's `tool_overrides` narrows `extra_allowed_hosts` to `[]` — request to `localhost:8484` is now blocked even though operator permits it. Validates the `Narrow` semantic on the allowlist field.
7. `fetch_url` on a public article — readability extraction returns markdown of main content.
8. `download_file` to in-scope path — file written; size matches.
9. `download_file` of a slow-large file — operator submits, switches conversations (verifies F4's WebSocket fixes hold for web tools too), rejoins, sees download in progress + history intact.

10th scenario (operator may run if time permits): `download_file` to out-of-scope path → `[error] [constraint] path '...' outside allowlist`. Largely covered by F3's filesystem-tool HAT; included only if the operator wants the thoroughness.

**Decision 12 — `SearchBackend` lifecycle (option a: registry alongside cross_configs)**:

- Backends are instantiated inside `BuiltinToolProvider.get_tools()` alongside the existing `cross_configs` dict — a parallel `_search_backends: dict[str, SearchBackend]` keyed by backend name (e.g., `"duckduckgo"`).
- `WebSearchTool.__init__` receives the resolved backend through the `cross_configs` dict: provider injects via `cross_configs[SearchBackend] = ddg_instance` (the `SearchBackend` Protocol is the dict key, same shape as `cross_configs[FilesystemConfig]` in F4). Tool reads `self._cross_configs[SearchBackend]` in `execute`.
- Backends carry an `httpx.AsyncClient` — lifecycle is per-`get_tools()` call, matching the agent's session-bound freshness contract (a session with `extra_allowed_hosts=[X]` gets a different httpx client than a session without).
- F5 ships only `DDGSearchBackend`; selection is a no-op until F6 admin UI exposes the picker. The protocol is in place so a second backend is a small leg in a future mission.
- **Rejected alternatives** (per architect review):
  - Module-level singletons (option b) — leak between agents with different `extra_allowed_hosts`.
  - Per-tool-init re-instantiation (option c) — re-creates 19 times per agent; wasteful.

The lifecycle aligns with the "session-bound freshness" contract documented in `agents.md`: any change to operator config takes effect at the next `AgentFactory.create()`.

### Prerequisites

- [x] M05 Flight 4 landed and merged to `main` (commit `1019022`).
- [x] Schema is at v8 (no schema changes in F5; verified `the_one/db/schema.py:9 CURRENT_VERSION = 8`).
- [x] `the_one/tools/resolver.py` ships `Narrow` / `NarrowSuperset` / `_check_narrow` / `resolve()` (F2 + F3 L1 + F4 L1b).
- [x] `the_one/tools/filesystem.py` ships `_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path`, `FilesystemConfig` (F3) — L0 will unify these.
- [x] `the_one/tools/base.py` ships `ConstraintError`, `Tool` ABC with `cross_configs`/`agent_name` (F4 L1b).
- [x] `the_one/tools/builtins.py` `_TOOL_CLASSES` has 17 entries (post-F4); F5 mods 2 existing (`http_request`, `web_search`) + adds 2 new (`fetch_url`, `download_file`) = 19 entries post-F5.
- [x] uvicorn `--reload` wired in `docker-compose.yml` (F4 follow-up `a41789a`); no manual restart needed during F5 iteration.
- [ ] Add `readability-lxml>=0.8` and `markdownify>=0.13` to `pyproject.toml` dependencies (lands in L1 with the dep-add commit, NOT pre-flight — keeps the pre-flight footprint small).
- [ ] **`lxml` runtime smoke**: `lxml` is NOT currently installed in the dev container (verified via `docker exec the-one python -c "import lxml"` → `ModuleNotFoundError`). `readability-lxml` requires `lxml`, which on `python:3.11-slim` historically required `apt-get install libxml2-dev libxslt1-dev`. Recent `lxml` 4.x+ ships manylinux wheels that are self-contained on x86_64. **L1 first step**: `pip install lxml` and verify import works. If wheel install succeeds (expected on x86_64), no Dockerfile changes needed. If it fails, L1 adds the apt-get line to the Dockerfile. Document outcome in flight log.
- [ ] No port/network conflicts — F5 doesn't introduce new services, ports, or env vars beyond the new web tool deps.
- [ ] User approves leg breakdown (Phase 4 sign-off).

### Pre-Flight Checklist
- [x] All open questions resolved (12/14; 2 leg-design-time at L3/L4)
- [x] Design decisions documented (12)
- [x] Prerequisites verified (7 of 9; 2 land with L1)
- [x] Validation approach defined → see Verification section
- [x] Legs defined → see Legs section below

---

## In-Flight

### Technical Approach

**Order rationale (9 legs after pre-flight, executed in dependency order):**

1. **L0 — Filesystem helper unification.** Refactor F3's `_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path` + F4's `_cwd_check` into a single dispatched helper with a `CheckMode` enum. Existing call sites become shims for back-compat. F3+F4 test suites pass unchanged. ~80 LoC + tests. Single-concern, mechanical.
2. **L1 — `WebConfig` + helpers + SSRF transport.** Defines the per-category Config (timeout pair, response-size cap, redirect cap, URL/host allowlist + denylist, extra_allowed_hosts) + `_url_check`, `_truncate_response`, `_is_ssrf_blocked`, `SSRFGuardedTransport`. Adds `readability-lxml` + `markdownify` deps. Tested in isolation; no tool wiring yet. **Includes a stub-tool consumer test** (per F4 debrief recommendation: scaffolding legs ship a consumer-facing test).
3. **L2 — Migrate `HttpRequestTool`.** Wire `Config = WebConfig`. Constraint enforcement at all sites: SSRF + allowlist + size cap + redirect cap + timeout. Three-clause envelope. Update existing tests; add new constraint-violation tests.
4. **L3 — `fetch_url` tool.** New tool. Routes through `SSRFGuardedTransport`. Content-type dispatch (HTML→readability+markdown, text/JSON→raw, binary→refuse-with-guidance). Tests cover all three branches.
5. **L4 — `download_file` tool.** New tool. `Config = WebConfig`, `Requires = (FilesystemConfig,)`. Streaming download with mid-stream size-cap abort. Path validation via the unified `_filesystem_check(mode=WRITE_NEW)`.
6. **L5 — `SearchBackend` protocol + `DDGSearchBackend`.** New module `the_one/tools/_search_backends.py`. Browser User-Agent fixes the F1 known issue. Tests use `httpx.MockTransport` to inject controlled DDG responses.
7. **L6 — Migrate `WebSearchTool` to use `SearchBackend`.** Tool wraps the backend; gets the backend instance via cross-Config-style injection from `BuiltinToolProvider`. Mission Open Question for F1 marked resolved.
8. **L7 — HAT (interactive; non-autonomous).** Operator-driven walkthrough of all 10 constraint scenarios (per Decision 11), including SSRF DNS-rebind and slow `download_file` UI rejoin.
9. **L8 — Integration verification.** Full unit + browser + AIAT live smoke; F5-specific regression sweeps; CLAUDE.md + agents.md refresh; mission Open Questions closed; `python_exec` exit-code-suffix change appended to mission Known Issues (per F4 debrief action item).

### Checkpoints

- [ ] **L0 helper unification landed** — `_filesystem_check(mode=)` is the single source of truth; F3 test suite passes unchanged; F4 `_cwd_check` is a thin shim.
- [ ] **`WebConfig` + helpers landed** — Pydantic Config with annotated fields + cross-field invariant; `SSRFGuardedTransport` resolves-then-pins; `_truncate_response` tail-preserves; full constraint-matrix tests.
- [ ] **`HttpRequestTool` migrated** — `Config = WebConfig`; SSRF + caps + allowlist + redirect; existing tests adapted; new tests for each constraint type.
- [ ] **`fetch_url` shipped** — readability+markdownify pipeline for HTML; raw body for text; refuse-with-guidance for binary; size-cap honored.
- [ ] **`download_file` shipped** — streaming write; mid-stream size-cap abort; path validation; partial-file cleanup on abort.
- [ ] **`SearchBackend` protocol + `DDGSearchBackend` shipped** — F1 known issue closed (browser User-Agent fixes DDG breakage); test confirms 10 results parsed from a mock DDG response.
- [ ] **`WebSearchTool` migrated** — wraps the backend; operator can swap backend via tool config in F6.
- [ ] **HAT pass complete** — operator-driven walkthrough of all 10 constraint types; agent recovers gracefully; SSRF DNS-rebind blocked; slow `download_file` doesn't break the WebSocket UI surface (post-F4 fixes hold for web tools).
- [ ] **Integration verified** — full unit suite green (modulo pre-existing CSS-token red); browser suite green (modulo pre-existing Playwright env gap); AIAT live smoke green (modulo default-agent-no-provider env gap); F5 regression sweeps return zero unexpected matches.

### Adaptation Criteria

**Divert if**:
- `SSRFGuardedTransport` proves infeasible against httpx 0.27's transport API (e.g., the `request.url.copy_with(host=ip)` rewrite breaks SNI). Fall back to a hostname-resolution check at policy time + a `transport=None` (default) httpx client, accepting the small DNS-rebind TOCTOU window. Document as Decision-revision; HAT explicitly tests the rebind case to confirm the fallback's exposure.
- `readability-lxml` requires a system-level `libxml2` that's not in the Python slim Docker image. Fall back to `trafilatura` (single dep, vendored XML parser). Document as Decision-revision; L3 leg-design picks the alternative.
- Per-call denylist on `URL host` proves hard to express clearly to small-model agents (false-positives or unclear error messages). Tighten the matching shape; document as Decision-revision.

**Acceptable variations**:
- Whether `_search_backends.py` lives at `the_one/tools/` or a new `the_one/integrations/` directory. Default: `the_one/tools/` for F5 (consistent with existing layout); `the_one/integrations/` is a future cleanup.
- Whether `SSRFGuardedTransport` is a class or a `httpx.AsyncBaseTransport` subclass — depends on httpx 0.27's exposed surface.
- Whether `_truncate_response` is a separate helper or an extension of F4's `_truncate_output`. Default: separate (different boundary semantics — single-stream, content-typed).

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `00-filesystem-helper-unification` — F4-deferred maintenance pass. Refactor `_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path`, and F4's `_cwd_check` into a single dispatched helper with a `CheckMode` enum. The dispatch tail must explicitly handle the four divergent post-canonicalize checks (per architect feedback): READ asserts existence, WRITE_NEW asserts parent exists + path doesn't exist OR existence is OK, WRITE_EXISTING asserts path exists, DIRECTORY asserts `is_dir()` after scope. The leg artifact must show all four branches in pseudocode so reviewers can confirm coverage. Existing call sites become thin shims (or are inlined). F3 + F4 test suites pass unchanged. Lock the dispatch contract via a new test exercising all four modes against the same in-scope path with different on-disk shapes. ~120 LoC + tests.

- [x] `01-web-config-and-helpers` — Define `WebConfig` Pydantic model in NEW `the_one/tools/_web_config.py` with: `timeout_seconds_default/max` (Narrow, default-le-max validator, mirrors F4 D1), `response_size_cap_bytes` (Narrow, dropdown ui_choices, mirrors F4 D2), `redirect_cap` (Field-only, NO marker — tool-level only per Decision 9), `url_allowlist` (NarrowPrefix, mirrors F3 path_allowlist), `url_denylist` (NarrowSuperset, default-empty), `extra_allowed_hosts` (Narrow list — agent narrows operator's set per Decision 7), all-frozen via `ConfigDict(frozen=True)`. Define `_url_check(url, cfg)`, `_is_ssrf_blocked(ip, extra_allowed_hosts)`, `_truncate_response(body, cfg, content_type)`, `SSRFGuardedTransport` (sets `request.extensions["sni_hostname"]` for SNI preservation per Decision 6). Add `readability-lxml>=0.8` and `markdownify>=0.13` to `pyproject.toml`; verify `lxml` wheel install works in the dev container (per Prerequisites). Stub-tool consumer test exercises the helper through a fake URL fetch (per F4 debrief recommendation). **Required regression tests**: (a) `redirect_cap` agent override raises `ValueError` with the resolver's exact message at `AgentFactory.create()` time (per Decision 9); (b) DNS-rebind unit test using `monkeypatch.setattr(socket, "getaddrinfo", ...)` — first resolution returns public IP and passes, second resolution returns `127.0.0.1` and is blocked (per Decision 6); (c) no `disable_ssrf`/`ssrf_disabled`/equivalent field exists on `WebConfig` (mission invariant lock). ~280 LoC + tests.

If L1 grows past ~350 LoC of source during implementation, split `WebConfig` model from `SSRFGuardedTransport` (Decision-revision via flight log).

- [x] `02-migrate-http-request-tool` — `HttpRequestTool` declares `Config = WebConfig`. Rewrite `execute(method, url, headers, body, timeout?)` to: (1) `_url_check(url, cfg)` — SSRF + allowlist + denylist; (2) clip timeout via `min(timeout, cfg.timeout_seconds_max); if <= 0: 1` (mirrors F4 L3 pattern); (3) build httpx.AsyncClient with `transport=SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)`, `max_redirects=cfg.redirect_cap`; (4) read body up to `cfg.response_size_cap_bytes` (streaming); (5) `_truncate_response`. Three-clause envelope. Update existing tests (`test_web_tools.py::TestHttpRequestTool`); add 8 new constraint tests (SSRF block, redirect cap, size cap, allowlist refuse, denylist refuse, timeout, agent-narrow on `extra_allowed_hosts`, two-clause envelope). ~80 LoC + tests.

- [x] `03-fetch-url-tool` — NEW tool `FetchUrlTool` in `the_one/tools/web.py`. `Config = WebConfig`. Single `url` parameter. Content-type dispatch: HTML → `readability_lxml.Document(html).summary()` → `markdownify.markdownify(...)`; text/JSON → decoded body up to size cap; binary → `[error] use download_file for binary content`. SSRF + allowlist + size cap. Three-clause envelope. Tests cover all three content-type branches + constraint violations. Register in `_TOOL_CLASSES`. ~100 LoC + tests.

- [x] `04-download-file-tool` — NEW tool `DownloadFileTool` in `the_one/tools/web.py`. `Config = WebConfig`, `Requires = (FilesystemConfig,)`. Parameters: `url` (required), `path` (required). Streaming download via `httpx.AsyncClient.stream()`, write to `path` validated through `_filesystem_check(path, fs_cfg, mode=WRITE_NEW)`. **`response_size_cap_bytes` is the on-disk cap for `download_file`** (NOT in-memory) — the helper streams chunks and aborts when total bytes written exceed the cap. Explicit shape:
   ```python
   async with client.stream("GET", url) as resp:
       try:
           with path.open("wb") as fh:
               total = 0
               async for chunk in resp.aiter_bytes():
                   if total + len(chunk) > cfg.response_size_cap_bytes:
                       raise ConstraintError(
                           f"response exceeded {cfg.response_size_cap_bytes} bytes; partial file removed"
                       )
                   fh.write(chunk); total += len(chunk)
       except ConstraintError:
           path.unlink(missing_ok=True); raise
   ```
   Three-clause envelope. Tests cover happy path, mid-stream abort + partial-file cleanup, out-of-scope path refuse, SSRF refuse, parent-doesnt-exist refuse. Register in `_TOOL_CLASSES`. ~120 LoC + tests.

- [x] `05-search-backend-protocol-and-ddg` — NEW module `the_one/tools/_search_backends.py` with `SearchResult` dataclass, `SearchBackend` Protocol, `DDGSearchBackend`. DDG impl POSTs to `https://html.duckduckgo.com/html/` with browser User-Agent (`Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ...`) — fixes F1 known issue. Parses `result__a` + `result__snippet` markers (verified pattern). Tests use `httpx.MockTransport` to inject controlled DDG HTML; assert 10 results parsed correctly + UA header sent. ~120 LoC + tests.

- [x] `06-migrate-web-search-tool` — `WebSearchTool` declares `Config = WebConfig`. Wraps `DDGSearchBackend` instance. The backend is constructed at `BuiltinToolProvider.get_tools()` time (similar to LLM providers — a pre-built instance, not per-call). Tool's `execute(query, max_results)` routes to `backend.search(...)`. Mission Open Question for F1 (DDG returns no results) marked resolved. ~30 LoC + tests.

- [x] `hat-web-walkthrough` *(interactive; non-autonomous)* — Operator drives the agent through 10 scenarios via `POST /api/chat` (per Decision 11 list above). Slow `download_file` scenario validates F4's WebSocket fixes hold for web tools. SSRF DNS-rebind scenario uses a monkeypatched `getaddrinfo` to confirm the resolve-then-pin defeats TOCTOU. Inline fixes for any error-string-clarity issues.

- [x] `08-integration-verification` — Full default unit suite (target: post-L6 baseline + ~80-100 net new tests; modulo pre-existing CSS-token red); browser suite green (modulo Playwright env gap); AIAT live smoke green (modulo default-agent env gap). F5 regression sweeps:
  ```bash
  rg -n 'class WebConfig' the_one/tools/                        # 1
  rg -n 'SSRFGuardedTransport' the_one/                          # 2+ (definition + at least 2 tools using it)
  rg -n '_TOOL_CLASSES' the_one/tools/builtins.py | wc -l        # 1 (count assertion 13→17→19)
  rg -n 'DEFAULT_USER_AGENT' the_one/tools/_search_backends.py   # 1+
  ```
  Documentation: update `agents.md` to reflect 19 tools + the 6 active constraint types (path scope, read-size cap, output cap, timeout caps, command denylist, **URL/host scope + SSRF** new in F5). Update `CLAUDE.md` with `WebConfig` shape + SSRF transport pattern. Append `python_exec` exit-code-suffix behavior change to mission Known Issues (per F4 debrief action item, deferred from F4). Mission Open Questions for F5-assigned items marked resolved.

---

## Post-Flight

### Completion Checklist

- [x] All legs landed (L0-L8; L7 is the HAT)
- [x] Filesystem helper unification clean; F3+F4 tests unchanged
- [x] `WebConfig` shipped with timeout pair + response-size cap + redirect cap + URL/host scope + extra_allowed_hosts
- [x] `HttpRequestTool` migrated; constraint tests cover all 6 constraint types
- [x] `FetchUrlTool` shipped; readability+markdownify pipeline; content-type dispatch
- [x] `DownloadFileTool` shipped; cross-Config dispatch on FilesystemConfig; mid-stream cap abort
- [x] `SearchBackend` protocol + `DDGSearchBackend` shipped; F1 known issue closed
- [x] `WebSearchTool` migrated; backend pluggable via tool config
- [x] SSRF resolve-then-pin verified by test (DNS-rebind case)
- [x] HAT pass complete
- [x] Default unit suite green (modulo pre-existing CSS-token red)
- [x] No regressions in F1-F4 surfaces
- [x] CLAUDE.md and agents.md refreshed with F5 changes
- [x] `python_exec` exit-code-suffix change appended to mission Known Issues
- [ ] Code committed; flight log updated; flight status set to `landed` *(awaiting Reviewer batch commit; flight-log + flight status set in this leg)*

### Verification

**Static (grep / read):**

```bash
rg -n 'class WebConfig' the_one/tools/                       # 1 match
rg -n 'class SSRFGuardedTransport' the_one/                  # 1 match
rg -n 'SSRFGuardedTransport(' the_one/tools/                 # 3+ (http_request, fetch_url, download_file)
rg -n 'extra_allowed_hosts' the_one/                         # several
rg -n 'class SearchBackend' the_one/tools/                   # 1 match (Protocol)
rg -n 'class DDGSearchBackend' the_one/tools/                # 1 match
rg -n 'CheckMode\.' the_one/tools/                           # several (post-L0 unification)
rg -n '_filesystem_check_write_parent\|_filesystem_check_write_path' the_one/tools/  # 0 (post-L0; old shims removed or kept as deprecation aliases)
```

**Dynamic (test suite):**

```bash
make test-unit
make test-browser
docker exec the-one pytest -m live tests/test_aiat.py

# SSRF block invariant smoke
docker exec the-one python -c "
import asyncio
from the_one.tools.web import HttpRequestTool
from the_one.tools._web_config import WebConfig
async def main():
    tool = HttpRequestTool(WebConfig())
    out = await tool.execute(method='GET', url='http://169.254.169.254/latest/meta-data/')
    assert '[error] [constraint]' in out, f'SSRF block did not fire: {out}'
    print('OK SSRF blocks cloud metadata')
asyncio.run(main())
"

# DDG search smoke (F1 known issue close)
docker exec the-one python -c "
import asyncio
from the_one.tools.web import WebSearchTool
from the_one.tools._web_config import WebConfig
async def main():
    tool = WebSearchTool(WebConfig())
    out = await tool.execute(query='python asyncio')
    # Expect 5+ results (DDG default page returns 10)
    assert out.count('- ') >= 5, f'DDG did not return results: {out[:200]}'
    print('OK DDG search returns results')
asyncio.run(main())
"
```

**Manual (HAT):** L7 walkthrough — operator drives the agent through 10 scenarios per Decision 11.
