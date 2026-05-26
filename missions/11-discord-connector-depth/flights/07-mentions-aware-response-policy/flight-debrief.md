# Flight Debrief: Mentions-Aware Response Policy

**Date**: 2026-05-26
**Flight**: [Mentions-Aware Response Policy](flight.md)
**Status**: landed
**Duration**: 2026-05-23 → 2026-05-26 (planning through landing, including the L12 HAT dogfood + six inline hotfixes)
**Legs Completed**: 12 of 12

## Outcome Assessment

### Objectives Achieved

F7 shipped the policy gate as designed. The Discord bot now engages on five explicit decision paths (DM → override → mention → account+agent always-listen+inference-yes → silence) rather than auto-relaying every inbound. Auto-relay became invariant on engaged turns; the legacy `auto_relay_platform_replies` field is retired across data, dispatcher, factory, and Studio UI. The L4 inline-prefix projection (`[from {peer} in #{channel}]: ...`) lands the peer-name + channel-name LLM-side context that closes F6 Rec #4. The new channel-context tools (`fetch_channel_history`, `fetch_thread_history`, `fetch_dm_history`, `list_visible_channels`) compose with the engaged agent. The Studio UI surfaces paired Always Listen toggles (account-level + per-agent) that drive both stored state and live cross-component sync via a new `CustomEvent` ('connector-account-always-listen-changed').

The L12 HAT ran end-to-end via the new behavior-test skill on mission-control, with a rewritten spec following same-observable-taxonomy and rendered-state-precedence disciplines. 9/9 final PASS; the run surfaced six pre-F7-or-latent bugs that landed as inline hotfixes (12.h–12.m) with their own tests and flight-log entries.

### Mission Criteria Advanced

- **#12** (mentions-aware response policy) — **CLOSED-BY-F7**. Engaged-vs-silent decision verified end-to-end through real Discord traffic + real Ollama inference gate + real Sonnet agent + real channel-context tool use.
- **#13** (peer-name attribution end-to-end) — **CLOSED-BY-F6+F7**. F6 landed the gateway → session → Chat UI segments; F7 closed the LLM-side projection (the deferred F6 Rec #4) via L4's `build_user_message_content` helper at `the_one/llm/base.py`.

## What Went Well

**The n=3 module lift (DD §6) is the cleanest architectural artifact of the flight.** `the_one/connectors/post_step_metadata.py` reads like reference code: three mutators (`tag_post_step_visibility`, `bind_peer_name`, `bind_channel_context`) each carry an explicit Touches/Skips contract in the docstring; non-overlap is verifiable by inspection alone; the composition contract (lock + try-block + python -O assertion-pairing invariants) is codified in the module docstring. The unique `messages[pre_step_len]` addressing per mutator makes conflict-by-construction provably impossible. This is the model for how future n=N codification lifts should land.

**Single-site provider projection (DD §5) preserved byte-equality** for legacy non-connector sessions. `build_user_message_content` at `the_one/llm/base.py:148-184` is the explicit mutation site the F6→F7 premise-revalidation audit demanded. The `is not None` discipline (not truthiness) preserves the empty-string round-trip invariant. OpenRouter inherits via `OpenAIProvider._to_api_message` with zero override — pinned by both `is`-comparison and a behavioural parity test in `tests/test_llm_provider_user_content_projection.py`. The audit step the flight artifact called for is visible as the parity tests + the convention citation in `agents.md`. Cleanest F6-Rec-closure of the mission to date.

**The 5-path decision tree implementation reads cleaner than the prose spec.** `_policy_gate_decision` returns `(should_engage, policy_audit)` as a single concern; the function-local `LLMProviderRepository` import respects the load-cycle convention without bleeding into module-level; the silent-branch terminal-return semantics (no lock, no `update_last_inbound`, audit-only) are surfaced as one append site in the caller. No compromise visible.

**Atomic-leg discipline held.** L5 retired `auto_relay_platform_replies` across data + dispatcher + factory + five JS sites in one slice, with legacy strip-on-validate keeping back-compat clean. L11 landed paired toggles + storage + cross-component sync + browser tests as a single atomic surface.

**The behavior-test methodology validated itself.** The L12 HAT's Witnessed pattern caught a real spec-author error (smoke step 1 INCONCLUSIVE → spec fix → PASS), surfaced a DOM-vs-rendered selector-targeting mismatch (DE step 2), and produced confident grounded verdicts on the four [mixed-frame] rows (steps 4 + 8). The five methodology lessons codified mid-run into mission-control's skill docs (Same Observable Taxonomy, Rendered State over Internal State, Cache-Defeat row convention, Active Precondition Verification, Execution Modes) immediately earned their keep on subsequent steps.

**Inline hotfix discipline worked.** Six hotfixes landed during the HAT — each with its own flight-log entry, tests where applicable, and visual verification. No scope creep beyond the surgical fix; all six retained the surrounding code's conventions.

## What Could Be Improved

### Process

- **Behavior-test execution itself was the biggest source of friction.** Operator-identified, end-of-run. The methodology around running the tests — apparatus quirks (Slate.js composer accepts only `ClipboardEvent` paste, never `fill`/`type_text`; chrome-devtools MCP workspace-root restrictions; agent budgets exhausted on long sleeps), spec-example phrasings the inference gate rejected, mid-iteration text-verification anti-patterns — consumed more clock time than the bugs surfaced. The skill design assumed live-agent SendMessage continuation; the resumed session forced re-spawn-per-step which compounded the per-step overhead. **The methodology now handles all of these explicitly** (per the mission-control `skill/wbt` commits this session), but a clean fresh-session re-run would be the real validation.
- **Single-line `grep` verification commands in leg specs broke on multi-line call sites.** L1, L3, L5, L8 all had this pattern; agents had to manually verify by reading. Spec authors should describe verification semantically or use AST-aware checks, not pretend to ship a runnable command that isn't.
- **The L11 spec authored no visual-rendering test, only DOM `data-testid` queries.** That's how the toggle-styling bugs (12.i / 12.j / 12.k) sat in main for an entire flight without being caught — `.checked` reads fine on an invisible toggle. An Architect at planning phase can't reasonably catch CSS-class-name typos or runtime type drift; this is an observability problem, not a design problem.

### Technical

- **`ToolResult.content: str` annotation is not runtime-enforced.** Pre-F7. F7 made it reachable via L10's `list[dict]`-returning channel-context tools. 12.l and 12.m are surgical coercions at *consumer* boundaries (Anthropic provider, telemetry projection) — the right shape for an inline hotfix, the wrong shape for a permanent fix. The proper fix is either `__post_init__` enforcement at `ToolResult` construction OR a widened annotation `str | dict | list` with codec + every consumer audited. The Anthropic provider still has `list`-shape branches that don't call the helper; any future provider added to the codebase will rediscover this bug.
- **`Message.content: str = ""` shares the same shape**. Anything that mutates `msg.content` via codec decode or post-step binding could land a non-str here; the provider audit re-validated USER-role only; ASSISTANT/SYSTEM branches still pass `msg.content` through unchanged.
- **GET/PUT mask sentinel asymmetry has one remaining site** at `api.py:1588` (POST `/test/connect` body-override) — explicitly out-of-scope for 12.h but worth a full sweep across MCP + connector + provider GETs to confirm every mask shape round-trips.
- **The mask-shape regex `^\*\*\*(\.\.\..{1,4})?$` is anchored on the GET-shape but shares no constant with `_mask_secret_value`'s output.** A future maintainer could change one and not the other, reintroducing the round-trip corruption silently — the existing tests only check the current shape. Single helper that GENERATES the mask AND matches it via shared regex literal would fix.
- **`.tool-enable-switch` defaults to `position: absolute`** (designed for tile-corner consumers); admin.css has accumulated n=4 override rules (`tools-editor-enabled-row`, `mf-sandbox-network-row`, `cf-auto-relay-row`, and the combined account-level + per-agent always-listen rows). The default is now the exception. Flip default to `position: relative`; tile-corner consumers opt in to `absolute`.
- **`session_metadata: dict[str, Any] | None`** receives the new `policy-silent` audit entries as free-shape JSON. F9's audit-log inspector (forthcoming) will need either a Pydantic discriminated-union or a JSON-schema check at write time before it can render unknown shapes safely.

### Documentation

- **Connectors plugin-author guide is still missing.** Deferred since F3; F7 added two new optional hooks (`fetch_history`, `fetch_dm_history` patterns) plus the new `is_mention` hook with no corresponding plugin-author doc.
- **`ToolResult.content` contract has no docstring** explaining what shapes are acceptable. Annotation lies; doc doesn't disambiguate.
- **`agents.md` is starting to feel long.** F7 added citations to four conventions and updated three more. The discipline is holding but a future flight may want to split by domain (codec / dispatcher / UI primitives / plugin hooks).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L8 reshaped the `last_inbound_at` test from "assert None on silent" to "capture-then-assert-unchanged" | `_session.py:resolve_session` sets `last_inbound_at` on creation, breaking the planned shape; reshaped test is a tighter regression net | Yes — capture-then-assert-unchanged is the better pattern for "doesn't mutate" claims about side-effecting code paths |
| Six inline hotfixes (12.h–12.m) during L12's HAT | Pre-F7 latent bugs surfaced by F7's L10/L11 reach; each fix was surgical, tested, flight-log'd inline | Yes — the discipline of "find bug → hotfix → test → re-verify → document" inside the HAT leg is the right pattern. The four CSS-toggle bugs (12.i/j/k) and the two serialization bugs (12.l/m) all caught by visual rendered-state observation, not DOM queries |
| Mid-flight skill rewrite: behavior-test methodology codified during the dogfood | The skill's "live agents via SendMessage" architecture wasn't available in the resumed session; the apparatus failures + spec-author error + DOM-vs-rendered divergence revealed the need for explicit fallback + frame discipline + rendered-state precedence rules | Yes — the mission-control commits (`fa8bdd1`, `ee52ced` on `skill/wbt`) codify the lessons; the behavior-test spec format is the artifact most worth reusing in the next flight per operator |
| Evidence files moved out of `tests/behavior/` to `/tmp/...` mid-flight | PII risk in screenshots/snapshots + repo bloat; evidence is cheap to regenerate | Yes — codified in mission-control `ee52ced` |
| Step 7's spec example question rejected by qwen2.5:7b inference gate | Conservative inference model biased against third-person framings; v3 substituted direct-address question and engaged correctly | Yes (methodology) — spec example questions should be pre-validated against the configured gate model, or the test harness should support equivalent-question substitution |

## Key Learnings

**Test metrics**: 2645 passed, 4 skipped, 12 deselected, 213.45s wall (non-browser suite via `uv run pytest tests/ --ignore=tests/browser --ignore=tests/behavior -x`). Compared to F2 baseline (2443 passed at 205.85s, 4 failed, 7 skipped): **+202 passes, +3.6% wall, –4 failures, –3 skips, no regressions**. The pre-existing chronic UI failure (`test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs`, ≥9 flights deep) lives in the browser suite and stays queued for routine-maintenance. The 30 new hotfix tests substantively exercise bug shapes (e.g., `test_get_put_get_does_not_corrupt_secret` does direct DB ciphertext decryption rather than relying on mask-shape comparison — the latter would silently pass on a corrupted value).

**Rendered State over Internal State is the most load-bearing methodology lesson.** Three of the six L12 hotfixes (12.i / 12.j / 12.k) would have been caught at L11 landing if the rendered-state discipline had existed at L11 planning. The L11 acceptance criteria asserted `.checked` and `data-testid` queries; both pass on a CSS-broken toggle. Future UI feature specs need rendered-chrome observables, not just DOM queryable observables.

**Same Observable Taxonomy with [mixed-frame] markers** worked cleanly. Steps 4 and 8 of the HAT exercised user-facing-silence with cross-frame audit-log confirmation; both verdicts cited the primary observable first and used the supplementary observable only to distinguish always-listen-off from inference-no. The discipline catches the case the user can't distinguish on their own.

**Inline-hotfix discipline scales further than expected.** Six hotfixes inside one HAT leg, each with own flight-log entry + tests + visual verification, didn't disrupt the leg's coherence. The HAT became "verify the spec + harden the dependencies that the spec exposed" — a useful framing.

**Methodology friction can exceed bug friction.** Operator identified this as the biggest cost. Apparatus quirks (Slate composer, MCP workspace roots, agent budgets), spec-example sensitivity to model behavior, and the fallback-mode-without-SendMessage all compounded. The methodology now codifies each of these; a fresh-session re-run on a clean spec would validate.

## Recommendations

1. **Open a follow-up flight for "Provider-shape-portability hardening"** scoped to: (a) `ToolResult.content` typing — pick between `__post_init__` enforcement or widened annotation with audited consumers; (b) `Message.content` audit for ASSISTANT/SYSTEM branches; (c) full GET/PUT mask sentinel sweep including `api.py:1588`; (d) cross-provider chat-history shape (task #25 — agent sessions accumulated under one provider not always sendable to another). All four share the runtime-unenforced-type-contract root cause.

2. **Add a "rendered-state observable" row to every UI feature spec, not just DOM queryability.** Specifically for L11-class work (toggles, tiles, forms): each interactive element needs an Expected Result phrased in user-perceivable terms ("toggle is visible as a styled iOS-pill with knob position X"), not internal terms (`#toggle.checked === true`). The behavior-test spec format already supports this; the lesson is to use it on UI legs from the start, not retrofit at HAT time.

3. **Pick up the four routine-maintenance candidates this flight surfaced**: (a) flip `.tool-enable-switch` CSS default from `absolute` to `relative` and have tile-corner consumers opt in (n=4 override rules signal the default is wrong); (b) hoist `_inbound.py` numbered steps to extracted helpers (file at 700+ lines, still readable but trending); (c) lift the studio-event-bus n=3 inline-CustomEvent pattern; (d) codify the field-row-3-column primitive (n=5 met with L11's two new rows). None are urgent; all are nominated by the L1–L11 work.

4. **Codify the inline-hotfix-during-HAT discipline as the standard for interactive legs.** Update the L12-style leg template (or the `/leg` skill's HAT branch) to anticipate: bugs will surface during the walk; the executor agent runs surgical Developer-agent fixes in-line; each fix gets a flight-log entry + test + visual verification; the HAT then resumes from the failing step. The F7 L12 entries (12.g–12.m) are a working example.

5. **Re-run the discord-engagement behavior test in a fresh session as the validation pass.** The L12 run dogfooded an evolving methodology; the spec is now stable, the skill is now stable, the project's `.flightops/` is now stable. A clean run would either confirm the methodology holds or surface remaining apparatus friction worth one more methodology lesson.

## Action Items

- [ ] Open a M11 follow-up flight artifact for provider-shape-portability hardening (recommendation #1 scope).
- [ ] Update `/leg` skill (or the leg template) to nominate a "rendered-state observable" row for any UI-touching acceptance criterion (recommendation #2).
- [ ] File a routine-maintenance entry capturing the four codebase candidates (recommendation #3) for the next `/routine-maintenance` pass to triage.
- [ ] Re-run `/behavior-test discord-engagement` in a fresh Claude Code session (recommendation #5); attach the run log to this debrief or open as a separate run log under `tests/behavior/discord-engagement/runs/`.
- [ ] Document the `is_mention`, `fetch_history`, and `fetch_dm_history` plugin hooks in a new `the_one/connectors/PLUGIN_AUTHORS.md` (or similar) — closes the F3-deferred gap and pre-empts F-future plugin work.
- [ ] Add a docstring to `ToolResult.content` (and `Message.content`) clarifying which shapes are acceptable at the wire; pin "must be str" or document "str | dict | list with serializer coercion" until the typing fix lands.
