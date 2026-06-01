# Leg: admits-inbound-refactor-to-admission-context-dataclass

**Status**: completed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

## Objective

Refactor `admits_inbound` to take a narrow frozen `AdmissionContext` dataclass instead of loose `peer_id`/`channel_id` + kwargs, so future ACL field additions become new dataclass fields that the type system forces every call site to supply — structurally preventing the Bug D failure mode (a call site silently using kwarg defaults). Option B per the operator's Phase 4 selection.

## Context

- **Why (Bug D structural prevention)**: Bug D (L1) was `_permitted_agents` calling `admits_inbound` with positional args, silently defaulting the `is_dm`/`guild_id`/`member_roles` kwargs. L1 fixed the call; L8 makes the whole CLASS of bug impossible — `admits_inbound(account, agent_acl, ctx)` with a required `AdmissionContext` means a new ACL axis = a new `AdmissionContext` field = a type error at every unmigrated call site.
- **Sequencing**: L8 lands AFTER L1 (done) so it migrates an already-correct `_commands.py` call site (a single-line shape change, not threading two changes in opposite directions).
- **L1 left the shared `envelope_is_dm(envelope, plugin)` helper** (`_acl.py:102`, getattr-sentinel honoring the plugin's `is_dm` hook, `plugin=None` → `_default_not_dm`). Both production call sites currently derive `is_dm`/`guild_id`/`member_roles` inline and identically. L8 folds that derivation INTO `AdmissionContext.from_envelope(envelope, plugin)` and removes the inline duplication. (Flight.md:96/161 mis-describes `_default_not_dm` as `not raw.get("is_dm")` — it returns plain `False`; `from_envelope` must reuse `envelope_is_dm`, NOT the flight's mis-stated formula. Per the L1 flight-log note.)
- **Two production call sites** (`git grep admits_inbound the_one/`): `_routing.py:177` (`_agent_admits`) and `_commands.py:124` (`_permitted_agents`). (`agents.md:515` is historical Bug-D narration, not a call site — leave it.)
- **Wrapper decision = option (b)** (flight DD, `test-translator-helpers-for-shape-evolution` convention): the test wrapper `admits_inbound(account, agent_acl, peer_id, channel_id, **kwargs)` at `tests/test_connectors_acl.py:37` STAYS as the flat-shape adapter — it builds `AdmissionContext` internally (+ its existing v24 translation + the `DEFAULT_TEST_GUILD_ID` default). The ~30+ flat-shape test call sites are UNCHANGED. Smaller diff; preserves test readability.
- **`admits_outbound` is NOT refactored** (two-symmetric-paths-in-acl convention): the F4 platform-send tool has no inbound envelope at outbound time, so there's nothing to build an `AdmissionContext` FROM. Its signature + test wrapper stay as-is. Verify at recon.
- **Internal split preserved**: `admits_inbound` keeps delegating to `_admits_inbound_dm` + `_admits_inbound_guild` (F12 L2) — it unpacks the 5 fields from `ctx` and calls them as before.

## Inputs

- `the_one/connectors/_acl.py` — `admits_inbound` (`:317`); `envelope_is_dm` (`:102`); `_admits_inbound_dm`/`_admits_inbound_guild`; `InboundEnvelope` already imported; `__all__`.
- `the_one/connectors/_routing.py:165-189` (`_agent_admits`) — inline derivation + 5-arg call at `:177`.
- `the_one/connectors/_commands.py:112-128` (`_permitted_agents`) — inline derivation + per-loop call at `:124`.
- `tests/test_connectors_acl.py:37-58` — the `admits_inbound`/`admits_outbound` flat-shape wrappers; `_admits_inbound_real` import; ~30+ call sites.
- `tests/_acl_shape_helpers.py` — `DEFAULT_TEST_GUILD_ID`, `_to_v24_agent_acl`, `_to_v24_shape` (no signature change).

## Outputs

- `@dataclass(frozen=True) class AdmissionContext` (5 fields + `from_envelope` classmethod) in `_acl.py`.
- `admits_inbound(account, agent_acl, ctx: AdmissionContext) -> tuple[bool, str]`.
- Both production call sites build the context via `AdmissionContext.from_envelope(envelope, plugin)`; inline derivation removed.
- Test wrapper builds `AdmissionContext` internally (option b); call sites unchanged.
- +3 `TestAdmissionContextConstruction` tests.

## Acceptance Criteria

- [ ] `AdmissionContext` is a `@dataclass(frozen=True)` near the top of `_acl.py` with exactly: `peer_id: str`, `channel_id: str`, `is_dm: bool`, `guild_id: str | None`, `member_roles: list[str]`. Add a `from_envelope(cls, envelope: InboundEnvelope, plugin: Any | None) -> AdmissionContext` classmethod that derives `is_dm` via `envelope_is_dm(envelope, plugin)` (NOT a raw read), `guild_id = envelope.raw.get("guild_id")`, `member_roles = envelope.raw.get("member_roles", [])`, `peer_id`/`channel_id` from the envelope. Export via `__all__`.
- [ ] `admits_inbound` signature is `admits_inbound(account: Connector, agent_acl: dict | None, ctx: AdmissionContext) -> tuple[bool, str]`. Body unpacks the 5 fields from `ctx` and delegates to the existing `_admits_inbound_dm`/`_admits_inbound_guild` split — NO semantic change vs post-L1 behavior.
- [ ] `_routing.py:_agent_admits` and `_commands.py:_permitted_agents` migrated to `admits_inbound(account, agent_acl, AdmissionContext.from_envelope(envelope, plugin))`; the inline `is_dm_value`/`guild_id`/`member_roles` derivation lines removed from both (now inside `from_envelope`). In `_permitted_agents`, build the context ONCE before the eligible-agents loop (it's agent-independent) and reuse it.
- [ ] Test wrapper `tests/test_connectors_acl.py:37` updated to build `AdmissionContext` internally from the flat kwargs (preserving the v24 `agent_acl` translation + the `is_dm`-false→`DEFAULT_TEST_GUILD_ID` default), then call the real `admits_inbound(account, v24_acl, ctx)`. The ~30+ flat-shape call sites stay UNCHANGED.
- [ ] **The wrapper CONSUMES `is_dm`/`guild_id`/`member_roles` from kwargs into the context and passes ONLY `(account, v24_acl, ctx)` to the real fn — NO residual `**kwargs` forwarding** (design-review medium catch: forwarding the now-consumed kwargs to the `(account, agent_acl, ctx)` signature would raise `TypeError`). Preserve the existing DM-context behavior: when `is_dm=True` the wrapper must NOT apply the `DEFAULT_TEST_GUILD_ID` default → `guild_id=None` flows into the context (the DM-context fixtures depend on this; `from_envelope` itself has no such default — the wrapper supplies it).
- [ ] `admits_outbound` + its test wrapper are UNTOUCHED (no envelope context; two-symmetric-paths convention). Recon-verify it has no `AdmissionContext`-shaped need.
- [ ] +3 `TestAdmissionContextConstruction` tests: `from_envelope` extracts `is_dm` via the plugin hook (and the `plugin=None` → `_default_not_dm`=False fallback), `guild_id`, and `member_roles` (defaulting `[]` when `raw` lacks it) correctly.
- [ ] **Grep gate (Phase 5c)**: `git grep -nE 'admits_inbound\(' the_one/ tests/` shows ALL production call sites passing an `AdmissionContext` (or `.from_envelope(...)`); ZERO production sites with positional `peer_id, channel_id, ...`. The test wrapper's signature stays kwarg-based BY DESIGN (it's the flat→context adapter) — that's allowed residue, flag it explicitly.
- [ ] Backend suite: prior backend count **+3** / 0 errors (the 3 construction tests; the ~30+ existing ACL tests pass unchanged via the wrapper). Record actuals.

## Verification Steps

- `docker exec the-one bash /app/scripts/run-tests.sh tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_commands.py -x --timeout 30 -q` — ACL + routing + command tests pass (the wrapper migration keeps the ~30+ flat-shape tests green).
- `docker exec the-one bash /app/scripts/run-tests.sh -m 'not browser and not live and not pixel' -q` — full backend at prior+3 / 0 errors (leg-end).
- `git grep -nE 'admits_inbound\(' the_one/ tests/` — production sites pass `AdmissionContext.from_envelope(...)`; only the test wrapper definition keeps the kwarg signature.

## Implementation Guidance

1. **Define `AdmissionContext`** near the top of `_acl.py` (after imports, before `admits_outbound`). `@dataclass(frozen=True)` (slots optional — match the file's other dataclasses). `from_envelope` reuses `envelope_is_dm(envelope, plugin)` for `is_dm`. Add to `__all__`.
2. **Change `admits_inbound`'s signature** to `(account, agent_acl, ctx)`. At the top of the body, unpack: `peer_id, channel_id, is_dm, guild_id, member_roles = ctx.peer_id, ctx.channel_id, ctx.is_dm, ctx.guild_id, ctx.member_roles`. Leave the rest of the body (the `_admits_inbound_dm`/`_admits_inbound_guild` delegation) unchanged. Update the docstring.
3. **Migrate `_routing.py:_agent_admits`**: delete the `is_dm_value`/`guild_id`/`member_roles` lines (`:168`,`:176-177`); call `admits_inbound(account, agent_acl, AdmissionContext.from_envelope(envelope, plugin))`. Verify routing tests pass unchanged.
4. **Migrate `_commands.py:_permitted_agents`**: delete the inline derivation (`:116-118`); build `ctx = AdmissionContext.from_envelope(envelope, plugin)` once before the loop; call `admits_inbound(account, agent_acl, ctx)` inside. Verify command tests pass unchanged.
5. **Update the test wrapper** (`tests/test_connectors_acl.py:37`): keep the flat `(account, agent_acl, peer_id, channel_id, **kwargs)` signature; internally apply the existing v24 `agent_acl` translation + the `is_dm`-false→`DEFAULT_TEST_GUILD_ID` default, then construct `AdmissionContext(peer_id=…, channel_id=…, is_dm=…, guild_id=…, member_roles=kwargs.get("member_roles", []))` and call `_admits_inbound_real(account, v24_acl, ctx)`. Import `AdmissionContext`.
6. **Add `TestAdmissionContextConstruction`** (3 tests) — build a minimal `InboundEnvelope` with `raw` carrying/omitting `guild_id`/`member_roles`/`is_dm`, pass a stub plugin (and `None`), assert the constructed context's fields.
7. **Run the grep gate**; record counts; verify `admits_outbound` untouched.

## Edge Cases

- **`from_envelope` with `plugin=None`** (test stub / pre-F8): `envelope_is_dm` falls back to `_default_not_dm` → `is_dm=False`. Pin in a construction test.
- **`member_roles` absent in `raw`** (pre-F8-L4 envelope): default `[]` — `from_envelope` must apply it (the dataclass field is non-optional `list[str]`).
- **Wrapper's `guild_id` default**: the existing wrapper defaults `guild_id=DEFAULT_TEST_GUILD_ID` when not a DM-context test and `guild_id` not passed — preserve this in the context construction so the ~30+ flat fixtures stay green.
- **Frozen dataclass + mutable `member_roles: list`**: a frozen dataclass with a list field is fine (the field is immutable-rebound, the list itself isn't deep-frozen) — matches the existing pattern; don't over-engineer with tuple conversion unless a test needs it.

## Files Affected

- `the_one/connectors/_acl.py` — `AdmissionContext` + `from_envelope`; `admits_inbound` signature/unpack; `__all__`.
- `the_one/connectors/_routing.py` — `_agent_admits` migrated.
- `the_one/connectors/_commands.py` — `_permitted_agents` migrated (context built once).
- `tests/test_connectors_acl.py` — wrapper builds `AdmissionContext`; +3 `TestAdmissionContextConstruction` tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — except commit, which is deferred to Phase 2d per agentic-workflow batch protocol:**

- [ ] All acceptance criteria verified (signature change, both call sites migrated, wrapper option-b, grep gate, +3 tests)
- [ ] Backend at prior+3 / 0 errors (wrapper used; actual count recorded); routing + command tests green unchanged
- [ ] `admits_outbound` confirmed untouched
- [ ] Update flight-log.md with L8 leg progress entry (signature, call sites migrated, grep-gate result, test count)
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off this leg in flight.md yet (Phase 2d)
- [ ] Do NOT commit (batched at Phase 2d)
