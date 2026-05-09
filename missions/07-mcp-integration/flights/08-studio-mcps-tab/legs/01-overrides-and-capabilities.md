# Leg: 01-overrides-and-capabilities

**Status**: completed
**Flight**: [Studio MCPs tab + inspector polish](../flight.md)

## Objective

Three coordinated backend changes that the Studio MCPs-tab UI (L3) builds on: (a) extend `StdioMCPOverride` and `StreamableHttpMCPOverride` with `enabled_tools` / `disabled_tools` reserved fields; (b) splice a per-source tool filter into `MCPToolProvider.get_tools_for_agent` between `list_tools()` and the `MCPClientTool` wrap loop; (c) add a `capabilities` field to the `/api/mcp-sources/{id}/test/connect` response sourced from `MCPClient.server_capabilities`.

## Context

- **Per-source toggle storage shape (Design Decision §1)**: extend the existing `mcp_overrides[source_name]` dict with two optional reserved sub-keys (`enabled_tools`, `disabled_tools`), un-prefixed server-side tool names. No reservation-validation needed — `mcp_overrides` is agent-side authored (via the L3 UI); `MCPSource.secrets` (operator-authored) is structurally separate. Pydantic v2 with `extra="ignore"` (project default per `_tool_provider.py` and the `model_config` on the existing override classes) accepts the new fields alongside credential keys without collision.
- **Filter splice point (Design Decision §1, locked at design review)**: between `mcp_tools = await client.list_tools()` (around `_tool_provider.py:229`) and the wrap loop that builds prefixed `MCPClientTool` instances (around `_tool_provider.py:256`). Filter on un-prefixed `mt.name`. Semantics mirror `AgentConfig.is_tool_enabled` at `agent/config.py:80` — if `enabled_tools` is non-None, only those tools pass; `disabled_tools` is always subtracted. The 64-char ceiling check inside the wrap loop runs only for tools that pass the filter (a disabled tool that would have failed the ceiling is skipped silently, no spurious warning).
- **Capabilities field (Design Decision §5)**: `MCPClient.server_capabilities` is **already a public property** at `the_one/mcp/client.py:189-194`, populated during `connect()` at line 397 from `result.capabilities`. No `MCPClient` changes; just `api.py::test_mcp_connection` reads `client.server_capabilities` after `list_tools()` and adds it to the `{status: "ok", tools: [...]}` payload at `api.py:876-886`. The `/test/connect` endpoint becomes the source of truth for what capability flags L2's UI renders above the tools list.
- **Resolver behavior on untagged fields — STRIP, do not pass**: the resolver in `the_one/tools/resolver.py:244-248` **raises `ValueError`** when it iterates a field that's in `agent_override` but lacks a `Narrow`/`NarrowPrefix`/`NarrowSuperset`/`Substitute` marker. So adding the new fields to `StdioMCPOverride`/`StreamableHttpMCPOverride` WITHOUT excluding them from `_apply_override`'s `resolve()` call would crash agent builds the moment any `enabled_tools` / `disabled_tools` payload is set. **Fix**: `_apply_override` strips the two reserved keys from `override_payload` BEFORE passing it to `resolve()`. The L1.2 filter site reads the un-stripped payload via `model_validate` directly — Pydantic validates all declared fields regardless of resolver markers, so the filter site sees the new fields normally. Per `_overrides.py`'s existing module docstring contract: "Future fields with a narrowing semantic ... can use Narrow without changing the schema shape" — but UNTAGGED fields require the strip-before-resolve dance because the resolver's locked-down "every field needs a marker" invariant predates the F8 reserved-key concept.
- **Filter must run AFTER `_apply_override`**: `_apply_override` at `_tool_provider.py:65-135` mutates `source.secrets` based on credentials only. The new `enabled_tools`/`disabled_tools` fields are read directly from the override payload (NOT from `effective_source.secrets`), and the filter applies to `list_tools()` output, NOT to the secrets dict. **`_apply_override` requires a one-line change** to strip the two reserved keys from the payload before calling `resolve()` (per the resolver-behavior bullet above) — see L1.2 implementation guidance.

## Inputs

- `the_one/mcp/_overrides.py` — declares `StdioMCPOverride` and `StreamableHttpMCPOverride`, both with `model_config = ConfigDict(frozen=True)`. Module is 83 lines; new fields go inside each class.
- `the_one/mcp/_tool_provider.py` — `MCPToolProvider.get_tools_for_agent` is at lines ~170-298. The filter splice is between line 229 (`mcp_tools = await client.list_tools()`) and line 256 (the `for mt in mcp_tools:` wrap loop).
- `the_one/interfaces/web/api.py::test_mcp_connection` — at lines 821-940. The Phase A success return is at lines 876-886.
- `the_one/mcp/client.py:189-194` — `server_capabilities` property already exists; lazily-checked-readable via the property after `connect()` succeeds.
- `tests/test_mcp_overrides.py` — existing override tests; new schema-acceptance test fits here.
- `tests/test_mcp_tool_provider.py` — existing provider-filter tests; new filter behavior tests fit here.
- `tests/test_oauth_test_connection_endpoint.py` (or wherever `/test/connect` is currently tested) — existing endpoint tests; new capabilities test fits here.

## Outputs

- `the_one/mcp/_overrides.py::StdioMCPOverride` and `::StreamableHttpMCPOverride` each gain two optional fields: `enabled_tools: list[str] | None = None` and `disabled_tools: list[str] | None = None`. Plain Pydantic fields (NOT `Annotated[..., Substitute]`) — the resolver doesn't dispatch on them.
- `the_one/mcp/_tool_provider.py::MCPToolProvider.get_tools_for_agent` reads the override payload's `enabled_tools` / `disabled_tools` fields and filters the `list_tools()` output before the wrap loop.
- `the_one/interfaces/web/api.py::test_mcp_connection` Phase A success returns add `capabilities` field sourced from `client.server_capabilities`. Phase B path (auth_required) is untouched (no capabilities visible until tokens land + a second click hits Phase A).
- New unit tests covering: schema acceptance (both override types), allowlist filter, denylist filter, intersection filter, edge cases, capabilities-on-success, capabilities-edge-case (server announcing `tools: {}, resources: None`).
- `flight-log.md` updated with L1 entry; leg status flipped to `landed`.

## Acceptance Criteria

- [ ] **L1.1** — `StdioMCPOverride(enabled_tools=["a","b"], disabled_tools=["c"], env={"K":"V"})` validates cleanly; `StreamableHttpMCPOverride(enabled_tools=["a","b"], disabled_tools=["c"], bearer_token="t", headers={"X":"Y"})` validates cleanly. Both fields default to `None`. The fields are NOT `Annotated[..., Substitute]` — the resolver MUST NOT pick them up. Verified by running `pytest tests/test_mcp_overrides.py -q --timeout 30 -x` — passes including any pre-existing marker-placement regression tests.
- [ ] **L1.2** — `MCPToolProvider.get_tools_for_agent` filters `mcp_tools` (output of `client.list_tools()`) before the `MCPClientTool` wrap loop, AND `_apply_override` is updated to strip the new reserved keys before its `resolve()` call:
  - If `enabled_tools` is `None`: no allowlist filter applied (current behavior preserved).
  - If `enabled_tools` is a list (incl. empty `[]`): only tools with `mt.name in enabled_tools` pass; an empty list filters out all tools from the source.
  - `disabled_tools` is ALWAYS subtracted: tools with `mt.name in disabled_tools` are removed.
  - Both lists are matched against **un-prefixed** `mt.name` (e.g. `"read_file"`, NOT `"mcp__github__read_file"`).
  - Order: enabled-list filter first, then disabled-list subtraction. (Equivalent to `is_tool_enabled` semantics on the existing `AgentConfig` field.)
  - The 64-char ceiling check inside the wrap loop runs ONLY for tools that pass the filter — a disabled tool that would have failed the ceiling is skipped silently, no spurious `MCPRegistrationError` log.
  - `_apply_override` MUST strip `enabled_tools` / `disabled_tools` from `override_payload` before passing it to `resolve()` (otherwise the resolver raises `ValueError` per `resolver.py:244-248` — verified at design-review time).
- [ ] **L1.3** — `POST /api/mcp-sources/{id}/test/connect` Phase A success response includes a `capabilities` key. The value is `MCPClient.server_capabilities`'s output (a JSON-serialized dict from `result.capabilities.model_dump(mode="json")`). Shape is preserved verbatim — no key renaming, no key invention; `None` values stay `None`. Phase B (auth_required) and error paths are unchanged.
- [ ] **L1.4** — Override-schema acceptance test in `tests/test_mcp_overrides.py` covers L1.1's positive cases plus a NEGATIVE case: `StdioMCPOverride(enabled_tools=["a"], **{"unknown_field": "x"})` validates cleanly (Pydantic `extra="ignore"` is the project default; this confirms unknown fields don't crash, matching the doc-comment in `_overrides.py:101-103`).
- [ ] **L1.5** — Provider filter unit tests in `tests/test_mcp_tool_provider.py` cover at minimum:
  - `enabled_tools` allowlist: source with tools `["read", "write", "delete"]` and `mcp_overrides={"src": {"enabled_tools": ["read"]}}` → registry contains only `mcp__src__read`.
  - `disabled_tools` denylist: same source with `{"disabled_tools": ["delete"]}` → registry contains `mcp__src__read` + `mcp__src__write`.
  - Intersection: `{"enabled_tools": ["read", "write"], "disabled_tools": ["write"]}` → registry contains only `mcp__src__read`.
  - Empty `enabled_tools` list: `{"enabled_tools": []}` → zero tools registered for that source.
  - `disabled_tools` naming a non-existent tool: no-op, no error.
  - No override entry for the source: full tool list registered (current behavior preserved).
- [ ] **L1.6** — `/test/connect` capabilities tests in `tests/test_oauth_test_connection_endpoint.py` (or the existing endpoint test home — implementer chooses based on the actual file layout) cover:
  - Success path returns `capabilities` matching the SDK's `result.capabilities.model_dump(mode="json")` shape.
  - Edge case: server announcing `{tools: {}, resources: None}` produces `capabilities.resources is None` in the response (no key invention; `model_dump`'s shape preserved).
- [ ] **L1.7** — `docker exec the-one pytest tests/ -q --timeout 30 -x --ignore=tests/browser` passes; no new failures vs L0 baseline (the L0-baseline failure on `test_acquire_lazy_spawn_creates_worker_and_returns_client` remains as documented known issue — not regressed BY L1).
- [ ] **L1.8** — `flight-log.md` gets a new "Leg Progress" entry naming each AC. Leg artifact's status is `landed` at end-of-leg.

## Verification Steps

1. **L1.1** — `docker exec the-one pytest tests/test_mcp_overrides.py -q --timeout 30 -x` — passes including the new acceptance test.
2. **L1.2** — `docker exec the-one pytest tests/test_mcp_tool_provider.py -q --timeout 30 -x` — passes including the new filter tests.
3. **L1.3 + L1.6** — `docker exec the-one pytest tests/test_oauth_test_connection_endpoint.py -q --timeout 30 -x` (or wherever `/test/connect` tests live) — passes including the new capabilities test.
4. **L1.4 + L1.5** — covered by L1.1 and L1.2 runs.
5. **L1.7** — `docker exec the-one pytest tests/ -q --timeout 30 -x --ignore=tests/browser` — passes (only the L0-baseline known issue still surfaces).
6. **L1.8** — open `flight-log.md`; new entry present.

## Implementation Guidance

### Order of operations

1. **L1.1** — extend `StdioMCPOverride` + `StreamableHttpMCPOverride`. Trivial — add two field declarations to each class.
2. **L1.4** — add the schema acceptance test (small).
3. **L1.2** — splice the filter into `_tool_provider.py`. ~10-15 LOC of filter logic.
4. **L1.5** — add the provider filter tests. ~80-120 LOC.
5. **L1.3** — extend `test_mcp_connection`'s Phase A success return with `capabilities`. ~3-5 LOC.
6. **L1.6** — add the `/test/connect` capabilities test.
7. Run the full suite per L1.7.

### L1.1 — Override schema extension

In `the_one/mcp/_overrides.py`, add two fields to BOTH classes:

```python
class StdioMCPOverride(BaseModel):
    model_config = ConfigDict(frozen=True)

    env: Annotated[dict[str, str] | None, Substitute] = None
    # F8 L1: per-source tool allow/deny. Plain fields (NOT Annotated
    # with Substitute/Narrow) — read directly from the validated
    # model in _tool_provider.py, not routed through the resolver.
    # Un-prefixed server-side tool names. None on enabled_tools means
    # "no allowlist applied"; an empty list means "no tools enabled".
    enabled_tools: list[str] | None = None
    disabled_tools: list[str] | None = None


class StreamableHttpMCPOverride(BaseModel):
    model_config = ConfigDict(frozen=True)

    headers: Annotated[dict[str, str] | None, Substitute] = None
    bearer_token: Annotated[str | None, Substitute] = None
    # F8 L1: see StdioMCPOverride for rationale.
    enabled_tools: list[str] | None = None
    disabled_tools: list[str] | None = None
```

**Important**: The fields are NOT `Annotated[..., Substitute]`. The resolver in `the_one/tools/resolver.py` looks for marker metadata on each field; untagged fields are skipped. Reading these fields requires going through the validated model directly, not via `resolve()`. (See L1.2 for the read site.)

### L1.2 — Filter splice in `_tool_provider.py` + `_apply_override` strip

**Two coordinated changes, both required.** The strip in `_apply_override` is mandatory: without it, the resolver raises `ValueError` on the new untagged fields and crashes the agent build.

#### Part 1: strip in `_apply_override`

In `the_one/mcp/_tool_provider.py:_apply_override`, modify the early body to strip the two reserved keys from `override_payload` before passing to `resolve()`:

```python
def _apply_override(
    source: MCPSource, override_payload: dict[str, Any] | None
) -> MCPSource:
    """..."""  # docstring unchanged
    if not override_payload:
        return source
    # F8 L1: strip reserved tool-filter keys before passing to resolve().
    # The resolver requires a Narrow/Substitute marker on every dispatched
    # field (resolver.py:244-248); the L1 reserved keys are intentionally
    # untagged because they're not credential substitutions — they're
    # consumed by the post-list_tools() filter in get_tools_for_agent.
    # Stripping here keeps the resolver contract clean.
    resolver_payload = {
        k: v for k, v in override_payload.items()
        if k not in ("enabled_tools", "disabled_tools")
    }
    if not resolver_payload:
        # Payload had ONLY tool-filter keys — no credential mutation needed.
        return source
    if source.type == "stdio":
        resolved = resolve(StdioMCPOverride, None, resolver_payload)
        # ... rest unchanged
```

The two reserved key names are hardcoded — matches the explicit "reserved field names" framing in flight Design Decision §1. (A future field could be added by extending the tuple; not in L1 scope.)

#### Part 2: filter splice in `get_tools_for_agent`

The splice point is between `_tool_provider.py:229` (`mcp_tools = await client.list_tools()`) and `_tool_provider.py:256` (the `for mt in mcp_tools:` wrap loop). Add:

```python
# F8 L1: per-source allow/deny filter. Read enabled_tools / disabled_tools
# from the validated override model. Filter on un-prefixed mt.name.
# Semantics mirror AgentConfig.is_tool_enabled: if enabled_tools is
# non-None, only those tools pass; disabled_tools is always subtracted.
override_model: StdioMCPOverride | StreamableHttpMCPOverride | None = None
if override_payload:
    if source.type == "stdio":
        override_model = StdioMCPOverride.model_validate(override_payload)
    elif source.type == "streamable-http":
        override_model = StreamableHttpMCPOverride.model_validate(override_payload)

if override_model is not None:
    enabled = override_model.enabled_tools
    disabled = override_model.disabled_tools or []
    if enabled is not None:
        mcp_tools = [mt for mt in mcp_tools if mt.name in enabled]
    if disabled:
        mcp_tools = [mt for mt in mcp_tools if mt.name not in disabled]
```

**Position**: insert this block AFTER line 229 (`mcp_tools = await client.list_tools()`) and BEFORE the comment block starting "# Wrap each MCPTool" around line 251. Indentation matches the surrounding `for source in sources:` body.

**Important — DO NOT call `resolve()` here**. Resolver dispatch crashes on untagged fields (verified `resolver.py:244-248`). The L1.2 filter calls `model_validate` directly to get the validated model with all declared fields populated. This is a deliberate divergence from `_apply_override`'s `resolve()`-based path.

**Edge case — Pydantic `ValidationError` on the model_validate call**: per the module docstring at `_tool_provider.py:33-35`, "Override application (failure: Pydantic ValidationError; we do NOT catch — operator schema mismatch is loud, not graceful-degrade)." So if `override_payload` is structurally malformed (e.g. `enabled_tools="not a list"`), `model_validate` raises and the agent build fails loud — same posture as `_apply_override`'s resolver path. This is correct.

**Note on double-validation**: the L1.2 model_validate is a second pass after `_apply_override`'s implicit one. Acceptable for this leg — Pydantic validation is fast (<1ms), the override payload is a small dict, and the cleanest separation keeps L1.2's filter independent of `_apply_override`'s mutation path. Optimization (single-validate, pass model through): possible follow-up but adds plumbing not justified by L1's scope.

### L1.3 — `/test/connect` capabilities

In `the_one/interfaces/web/api.py` `test_mcp_connection`, the Phase A success return at lines 876-886 currently looks like:

```python
async with MCPClient(source=source, auth_provider=provider_a) as client:
    tools = await client.list_tools()
return {
    "status": "ok",
    "tools": [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in tools
    ],
}
```

Extend to read `client.server_capabilities` while still inside the `async with` block. The property is populated during `connect()` (which `MCPClient.__aenter__` calls), so it's safe to read after `list_tools()` succeeds.

```python
async with MCPClient(source=source, auth_provider=provider_a) as client:
    tools = await client.list_tools()
    capabilities = client.server_capabilities  # F8 L1: snapshot before async-with exits
return {
    "status": "ok",
    "tools": [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in tools
    ],
    "capabilities": capabilities,
}
```

**Important**: read `server_capabilities` INSIDE the `async with` block, NOT after. Once the context manager exits, `_is_alive` flips False and the property's guard raises `MCPConnectionError`.

**No Phase B change**: Phase B (auth_required) doesn't return `status: ok`, so capabilities aren't surfaced there. Once tokens land and the operator clicks Test again, Phase A handles the second click and includes capabilities. This is fine — L2's UI renders capabilities only after a successful Test.

### L1.4 — Override schema test

Add to `tests/test_mcp_overrides.py`:

```python
def test_stdio_override_accepts_enabled_disabled_tools_alongside_env() -> None:
    """L1: per-source tool allow/deny fields validate alongside env."""
    o = StdioMCPOverride(
        env={"K": "V"},
        enabled_tools=["a", "b"],
        disabled_tools=["c"],
    )
    assert o.env == {"K": "V"}
    assert o.enabled_tools == ["a", "b"]
    assert o.disabled_tools == ["c"]


def test_streamable_http_override_accepts_enabled_disabled_tools_alongside_creds() -> None:
    """L1: per-source tool allow/deny fields validate alongside bearer/headers."""
    o = StreamableHttpMCPOverride(
        bearer_token="tok",
        headers={"X": "Y"},
        enabled_tools=["a"],
        disabled_tools=[],
    )
    assert o.bearer_token == "tok"
    assert o.enabled_tools == ["a"]
    assert o.disabled_tools == []


def test_stdio_override_extra_fields_ignored() -> None:
    """L1: Pydantic extra='ignore' (project default) silently drops unknown keys.

    Documents that a typo'd field name (e.g. `enabled_tool` vs `enabled_tools`)
    will NOT raise — operator gets the no-op behavior, same as bear_token vs
    bearer_token at _overrides.py:101-103.
    """
    # Should NOT raise.
    o = StdioMCPOverride.model_validate({"enabled_tool": ["typo"]})  # singular
    assert o.enabled_tools is None  # the typo'd value was dropped
```

**Important**: also verify that L1.1's marker-placement-regression test (if present in the file) STILL passes — adding new fields shouldn't disturb the marker introspection on existing fields.

### L1.5 — Provider filter tests

Add to `tests/test_mcp_tool_provider.py`. The existing tests there already exercise `MCPToolProvider.get_tools_for_agent`; mirror their fixture / setup pattern. Key fixtures:
- A stub `MCPClient` returning a controlled `list_tools()` output.
- An `AgentConfig` with `mcp_source_ids` and `mcp_overrides` populated.
- A `MCPSourceRepository` stub returning a known source.

Sketch (NOT a complete file — implementer adapts to the actual existing test pattern):

```python
async def test_get_tools_for_agent_applies_enabled_tools_allowlist(
    monkeypatch, /* existing fixtures */
) -> None:
    # Source has 3 tools.
    # Override: enabled_tools=["read"]
    # Expect: registry contains only "mcp__src__read"
    ...

async def test_get_tools_for_agent_applies_disabled_tools_denylist(...): ...
async def test_get_tools_for_agent_applies_intersection_filter(...): ...
async def test_get_tools_for_agent_empty_enabled_list_drops_all(...): ...
async def test_get_tools_for_agent_disabled_unknown_tool_is_noop(...): ...
async def test_get_tools_for_agent_no_override_entry_passes_through_full_list(...): ...
```

Look at the existing test patterns in the file — likely there's a helper for spawning a stub provider with controlled `list_tools` output. Reuse that.

### L1.6 — `/test/connect` capabilities tests

Append to `tests/test_oauth_test_connection_endpoint.py` (verified at design-review time as the existing endpoint test home). Sketch:

```python
async def test_test_connect_success_includes_capabilities(...) -> None:
    """L1.3: Phase A success return surfaces server_capabilities."""
    # Set up source with tokens; stub MCPClient to return capabilities matching
    # a known shape from result.capabilities.model_dump(mode="json").
    ...
    response = await client.post(f"/api/mcp-sources/{source_id}/test/connect")
    assert response.json()["status"] == "ok"
    assert response.json()["capabilities"]["tools"] == {}  # whatever the stub returned


async def test_test_connect_capabilities_preserves_none_values(...) -> None:
    """L1.6: model_dump's shape stays verbatim — None values are NOT dropped or renamed."""
    ...
    response = await client.post(f"/api/mcp-sources/{source_id}/test/connect")
    assert response.json()["capabilities"]["resources"] is None
```

## Edge Cases

- **Override payload with ONLY enabled/disabled fields, no credentials**: `_apply_override` strips the two reserved keys (per Part 1 of L1.2 implementation guidance), then checks if the post-strip payload is empty — if so, returns the source unchanged WITHOUT calling `resolve()`. Filter still applies via the L1.2 splice block on the un-stripped payload. Tested via L1.5's "no override entry for the source" / "enabled_tools alone" cases.
- **`enabled_tools` matches NO tool from `list_tools()`**: result is an empty `mcp_tools` list, so the agent registry gets zero tools from this source. This is intentional — operators can configure "attach this source but expose no tools" as a temporary disable. No log warning (the operator chose this).
- **Both `enabled_tools` and `disabled_tools` set, with the same tool in both**: enabled-list filter passes the tool; disabled-list subtracts it. Result: tool excluded. Documented behavior; tested in L1.5.
- **Override-payload model_validate raises ValidationError** (e.g. `enabled_tools="oops"`): per the module docstring contract, NOT caught — agent build fails loud. Same posture as `_apply_override`'s resolver path. Tested implicitly by the existing override-failure tests in `_apply_override`.
- **`server_capabilities` raises** (only happens if `_is_alive=False`): inside `async with MCPClient(...) as client:`, `_is_alive` is True after `__aenter__`. So the property doesn't raise. If a future refactor moves the read outside the block, the guard raises `MCPConnectionError` — but L1.3 is explicit about reading INSIDE the block.
- **`client.server_capabilities` returns dict with non-JSON-serializable value**: shouldn't happen — `model_dump(mode="json")` produces JSON-safe types. If it does happen, FastAPI's response serializer raises and the endpoint returns 500. NOT L1's responsibility to defend.
- **Phase B return shape**: untouched. Once OAuth completes, the operator clicks Test again and Phase A's branch surfaces capabilities. Single-flow contract.
- **Order matters in the filter**: enabled-list filter MUST run before disabled-list subtraction. If reversed, an empty `enabled_tools` list (which means "no tools allowed") would compute to `[]`, then disabled-list subtraction would no-op on an empty list — same outcome. But reversing isn't semantically clean. Stick to enabled-then-disabled to mirror `is_tool_enabled` at `agent/config.py:80-86`.

## Files Affected

- `the_one/mcp/_overrides.py` — extend two classes with two new fields each. ~6 lines added; comments add ~6 more. ~12 lines net.
- `the_one/mcp/_tool_provider.py` — TWO changes: (a) modify `_apply_override` to strip `enabled_tools`/`disabled_tools` from the payload before `resolve()` (~6 lines added in the function body); (b) add filter block between line 229 and the wrap loop (~12-18 lines added).
- `the_one/interfaces/web/api.py` — extend Phase A return with `capabilities`. ~3 lines added (1 capture line + 1 dict key + comments).
- `tests/test_mcp_overrides.py` — add 3 tests. ~30-50 lines.
- `tests/test_mcp_tool_provider.py` — add 6 tests. ~150-200 lines (includes fixture re-use boilerplate).
- `tests/test_oauth_test_connection_endpoint.py` — add 2 tests. ~40-60 lines.
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/flight-log.md` — append L1 progress entry.
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/flight.md` — check off L1 (final commit step at flight close).
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/legs/01-overrides-and-capabilities.md` — update status to `landed` (final commit step at flight close).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `docker exec the-one pytest tests/test_mcp_overrides.py tests/test_mcp_tool_provider.py -q --timeout 30 -x` passes
- [ ] `/test/connect` test file passes
- [ ] Default-suite scoped run passes (no new failures vs L0 baseline)
- [ ] Update `flight-log.md` with the L1 progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT commit yet — orchestrator batches code review + commit at flight end
- [ ] Signal `[HANDOFF:review-needed]`

## Citation Audit

12 citations verified against current code at leg design time:

- `_overrides.py:StdioMCPOverride` (line 45 — `class StdioMCPOverride(BaseModel):`) — **OK**, structure verified.
- `_overrides.py:StreamableHttpMCPOverride` (line 63 — `class StreamableHttpMCPOverride(BaseModel):`) — **OK**.
- `_overrides.py:101-103` (extra="ignore" doc-comment about bear_token typo) — **OK**.
- `_tool_provider.py:229` (`mcp_tools = await client.list_tools()`) — **OK**.
- `_tool_provider.py:255-256` (start of wrap loop `for mt in mcp_tools:`) — **OK** (verified at line 256: `for mt in mcp_tools:`).
- `_tool_provider.py:65-135` (`_apply_override` function) — **OK**.
- `_tool_provider.py:33-35` (module docstring on Pydantic ValidationError "loud, not graceful-degrade") — **OK**.
- `client.py:189-194` (`server_capabilities` property) — **OK**.
- `client.py:415` (line setting `self._capabilities = result.capabilities`) — **OK** (corrected from drifted citation `client.py:397` after design review).
- `the_one/tools/resolver.py:244-248` (the `marker_count == 0` ValueError raise) — **OK**, verified during design review.
- `api.py:821` (`@router.post("/mcp-sources/{source_id}/test/connect")`) — **OK**.
- `api.py:876-886` (Phase A success return block) — **OK**, verified 11-line block returning `{"status": "ok", "tools": [...]}`.
- `agent/config.py:80-86` (`is_tool_enabled` method) — **OK**.
- `tests/test_mcp_overrides.py:18` (existing `TestMarkerPlacementRegression`) — **OK**, found via grep.

No drift detected; no repairs needed.
