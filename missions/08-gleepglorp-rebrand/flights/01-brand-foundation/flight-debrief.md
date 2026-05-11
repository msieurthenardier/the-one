# Flight Debrief: Brand Foundation

**Date**: 2026-05-11
**Flight**: [Brand Foundation](flight.md)
**Status**: landed
**Duration**: 2026-05-11 (single-day flight, orchestrated via `/agentic-workflow`)
**Legs Completed**: 5 of 5

## Outcome Assessment

### Objectives Achieved

The flight replaced the cyan-accented "the-one" identity with the GleepGlorp AI purple-led identity across every user-visible surface, while preserving every internal identifier (Python module `the_one`, CLI binary `the-one`, MCP `clientInfo.name`, PyPI distribution name, test-internal fixture slugs). The brand substrate every downstream polish flight will build on is in place:

- 7 favicon size variants + multi-resolution `.ico` + 24×24 topbar icon, regenerated at HAT from the operator's preferred `gleepglorp_icon.png` (simpler head-crop variant) via `make brand-assets`
- Violet `--accent` palette (`#a78bfa` dark / `#6d28d9` light) and complementary teal `--accent-api` retune across all 6 accent-* token variants in both themes
- 62 cyan-color-in-class-name references mechanically renamed to `*-primary` (color-agnostic, decoupling future palette changes from JS HTML-string rewrites)
- 8 user-visible "the-one" → "GleepGlorp AI" surfaces rebranded
- WCAG 2.1 AA verified across the new palette including 3 new `accent_api` parametrizations
- 10 of 12 visual snapshot baselines regenerated cleanly

### Mission Criteria Advanced

| Criterion | Status | Notes |
|---|---|---|
| Product's user-facing identity reads as "GleepGlorp AI" consistently | Met | All 8 enumerated brand-text surfaces rewritten; ~25-30 preserved hits in `the_one/` are all internal (module, binary, protocol, pip hints, code comments) |
| Coherent visual identity anchored to logo + purple-led palette | Partially met | Palette and assets landed mission-wide; Flight 2 (Design Language: Robot/Control Panel) will refine the palette in aesthetic context |
| Color contrast meets WCAG AA for text, interactive elements, focus indicators | Met | WCAG audit green; 3 new `accent_api` text-on-color parametrizations close a previously-silent slot at `chat.css:94` |
| All existing M01-M07 capabilities continue working | Met | Narrow test gate (56 tests) green; `make verify-serving` exit 0; both reviewers confirmed |
| Browser tests pass; local visual-snapshot baselines regenerate cleanly | Mostly met | 10/12 baselines regenerated; remaining 2 (`chat_with_messages` × dark + light) blocked by pre-existing `app_with_agent` seeder issue logged as mission Known Issue |

## What Went Well

- **Token-value-change strategy.** Changing `--accent` value while keeping the token name absorbed 164 CSS references with zero downstream CSS edits required. The mental-model tax (`--accent` reads "cyan" in name but renders violet) is paid down by historical-context comments in `tokens.css:1-5`. No regret.
- **`--accent-api` recycled-cyan-as-secondary.** Reused the retired cyan-400/cyan-700 in the secondary slot — preserves chat user-vs-API differentiation without inventing a third hue. Bonus: closed a previously-silent WCAG audit gap on this token.
- **Hard cutover on class rename.** 62 → 0/62 hit-count symmetry confirmed. No CSS-alias debt left behind. `sed -i` plus targeted Edit for the two title-case comment headers was the right sequencing.
- **Snapshot baselines deferred to leg 05.** Legs 1-4 ran narrow gates with zero stale-baseline pollution; leg 5 regenerated against final state in one pass. `pyproject.toml`'s `addopts = "-m 'not pixel'"` was the load-bearing fact that made this cadence work — surfaced in flight design's open questions, validated by the implementation.
- **Design-review per leg caught real issues.** Two high-severity blockers in Leg 01 (scripts/ not bind-mounted; `docker compose run` vs `docker exec` convention drift), Leg 02's missed `--nav-fg-active` retune, Leg 03's 5 uncited `agents.md` hits + `CLAUDE.md:89`, Leg 04's wrong `the-one --version` flag dispatch. Without this gate, all would have surfaced as rework. The "Developer reviews leg design" step is the most-effective control in the orchestrator's protocol.
- **M04 design-system substrate is more resilient than expected.** Tokens / `.area-{id}` scoping / `App` namespace / component primitives absorbed a full palette swap with zero structural change. The substrate proved capable of being retuned in place rather than redesigned.
- **`agents.md` "annotate as historical" vs "rewrite" policy.** The Leg 03 per-line judgment for the audit-retune narrative (lines ~622, 632-655) preserved the leg-07 cyan-iteration story (which Leg 02 had no equivalent for, since the violet starter palette passed audit on first run). Reviewers landing there now see both stories layered.
- **Grep-as-acceptance-criteria pattern.** Each leg used grep-based zero-hit assertions for "what shouldn't be there anymore" plus count-bound assertions for "what should be there now." This shape is verifiable, mechanical, and produces unambiguous pass/fail signals. Worth canonizing.

## What Could Be Improved

### Process

- **Brand-foundation flights should grep three dimensions, not one.** The flight design grepped only `the-one` (brand string). The `cyan` and `NEXUS` (old palette code-name) dimensions surfaced via the leg-03 design review as 5 uncited `agents.md` hits + `CLAUDE.md:89` + the carry-over at `api.py:1478`. Catching them at design review was the safety net, but the primary control should have been a three-axis pre-flight grep: (a) brand string, (b) old palette hue, (c) old palette code-name.
- **`--nav-fg-active` scope-in was a process gap.** The hardcoded `#22d3ee` at `tokens.css:208` (inside the light-theme nav-rail block) was not auto-scoped-in by the flight's palette enumeration because the flight only listed `--accent` and `--accent-*` derivatives. Developer surfaced it at Leg 02 design review. A `grep -E '#[0-9a-f]{3,6}' tokens.css` step inside palette-flight design would auto-find all hardcoded brand-aligned hex values regardless of which token they live under.
- **Flight prerequisites should document the narrow-gate fallback when broad-suite hang is a known risk.** Leg 01's 17-minute pytest hang on `futex_wait_queue` was the first encounter with the SQLite WAL anomaly (live uvicorn holds `/root/.the-one/the-one.db`, pytest subprocess contends on it). It re-surfaced in legs 02-05 implicitly. CLAUDE.md:411 references "Always pair pytest with `-x`" but doesn't pre-warn that the broad suite hangs in the dev container. Future flights in this project should explicitly state the narrow-gate substitute in flight prerequisites rather than discovering it under leg-time pressure.
- **Per-surface decision table was incomplete.** Beyond the three-dimension grep gap above, the leg-04 brand-text design review surfaced `api.py:1478` (carry-over from leg 03), `tools-editor.js:56` `'the one cli agent'` (preserve), `tests/test_llm_registry.py:135` (preserve), and the wrong `--version` flag dispatch. All caught at review; cheaper to have been pre-enumerated.

### Technical

- **MCP-tab tool checkbox CSS is the third per-area checkbox treatment.** `admin.css:166-221` styles the iOS-toggle pattern with dual `.area-admin` / `.area-studio` selectors; the new `studio.css:171-209` block styles a different shape for MCP tab. When Flight 3 (Admin Polish) or Flight 4 (Studio Polish) touch checkboxes elsewhere, **extract a `.checkbox-primary` primitive to `components.css`** rather than writing a fourth treatment. Roughly a 30-line lift.
- **`DEFAULT_SOURCE` icon-file switch is untested.** `scripts/derive_brand_assets.py:35` points at `gleepglorp_icon.png`; if the file is ever deleted (because "we don't use the original anymore"), `make brand-assets` errors at runtime instead of failing a fast test. Cheap fix: assertion that `DEFAULT_SOURCE.exists()` in a unit test, OR a `# DO NOT DELETE — DEFAULT_SOURCE` marker comment alongside the source PNG in the brand directory.
- **The 2 chat-with-messages snapshot failures localize to `chat.js:99` `updateAgentBadge(name)`** which is fed by the `data.agent_name` handler at `chat.js:630`. In the `app_with_agent` fixture flow the seeded session-join WS message doesn't carry `agent_name`, leaving `<h2 class="session-agent-badge">` empty. This is the same code path Flight 5 (Chat Response Trace) will touch for persistence and `_send_pause_snapshot_if_needed` work — Flight 5 is the natural home to fix the seeder.

### Documentation

- **`agents.md` has no entry for the topbar mascot-icon CLS contract.** `components.css:30-34` (`.app-topbar-title img { width: 24px; height: 24px; flex-shrink: 0; }`) is load-bearing for "no layout shift on first paint" but reads as cosmetic styling. A future flight that restructures the topbar layout (Flight 2 may do this for the robot/control-panel aesthetic) will discover this contract empirically. One-line note in the design-system section.
- **Three patterns from Flight 1 deserve promotion to project-wide convention** (per Architect):
  1. **Dynamic `__version__` interpolation** (cli.py:30 piggyback) — promote to `agents.md`: no file hardcodes the version string; all version-bearing strings `from the_one import __version__` and f-string.
  2. **`docker-compose.yml ./scripts:/app/scripts:ro` bind-mount pattern** — codify in `CLAUDE.md` near the existing dev-iteration section so future utility scripts follow the convention.
  3. **`_ensure-playwright` post-rebuild requirement** — small footnote in CLAUDE.md Testing section: snapshot regeneration requires `make _ensure-playwright` after every `make rebuild` because the browser cache is in a named volume that survives but the deps go missing after image rebuild. Existing Makefile target is sufficient mitigation; the docs gap is the issue.
- **`agents.md` "Affordance patterns" subsection is overdue** (carried forward from M04 F02 debrief action items). Leg 03 refreshed the *vocabulary* (filled-primary, outlined-primary) but didn't *codify the affordance patterns explicitly*. Flight 2 will re-derive them inconsistently if this stays implicit.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Narrow test gate substituted for broad pytest (legs 01-05) | SQLite WAL contention between live uvicorn and pytest subprocess; broad-gate hung indefinitely | Yes — document narrow-gate-as-default in flight prereqs for this project until the underlying isolation is fixed |
| `gleepglorp_icon.png` retained at leg 01 as "future enhancement source"; became the actual default at leg 05 | Operator preferred simpler head-crop after seeing emblem favicons at small sizes during HAT | Per-flight judgment — but the retention-with-future-enhancement-note pattern is a good "low-cost option to keep available" template |
| Leg 03 carried `api.py:1478` cyan reference to Leg 04 | Same comment mixed brand-text + cyan-palette references; combining into one Leg 04 edit avoided re-edit collision | Yes — when a single source location has mixed concerns across two legs' scopes, defer to the later leg that will rewrite anyway |
| Dynamic `__version__` piggyback in Leg 04's `cli.py` rewrite | Stale `v0.1.0` literal was caught at design review while the line was being rewritten anyway | Yes — appropriate hygiene; opportunistic adjacent fixes that don't expand testing surface should be encouraged at design-review caught moments |
| Leg 03 5 uncited `agents.md` hits + `CLAUDE.md:89` added to scope at review | Three-dimension grep gap (brand + cyan + NEXUS) — design only grepped brand string | Yes — palette/brand-foundation flights should pre-grep all three dimensions |
| Leg 02 `--nav-fg-active` retune scope-in at review | Hardcoded hex inside the light-theme nav-rail block, not derived from `--accent` | Yes — `grep -E '#[0-9a-f]{3,6}' tokens.css` step in palette-flight design |
| Reviewer ran `ruff format` mid-review and absorbed ~94-line collapse in `api.py` | Project pins `ruff format --check` in CI per M07 maintenance; pre-existing format debt would have failed CI post-merge | Per-flight judgment — but the underlying issue is project-wide; a one-off `ruff format the_one/ tests/` at routine-maintenance cadence would prevent reviewers from absorbing per-flight |
| Stale `.admin-category-item` → `.section-nav-item` snapshot test fix at Leg 05 | Pixel suite excluded from default `addopts` so M04/M05 class rename rot went silent for months | Yes — `pytest --collect-only -m pixel` enumeration when renaming HTML classes (already added to mission Known Issues as preventive note) |

## Key Learnings

- **Design-review per leg is the highest-ROI control in the orchestrator's protocol.** Eight high/medium issues caught across four leg reviews would have surfaced as rework if absent. Worth the spawn-an-agent latency in every case.
- **Token-value retune cleanly absorbs into a token-driven design system; class-name rename is a separable concern.** These two paths interacted but didn't collide — the same flight handled both because they're sequenced, not concurrent. Future palette work should follow the same pattern.
- **Multi-dimensional pre-flight greps catch what single-dimension greps miss.** Brand-foundation flights especially benefit from grepping (a) brand string, (b) old palette hue, (c) old palette code-name, (d) hardcoded brand-aligned hex values across token files. Each dimension catches a different class of stale reference.
- **Operator HAT generates higher-signal feedback than pre-design grep can ever produce.** The icon source-PNG switch (`gleepglorp_icon.png` over `gleepglorp_med.png`) and the unstyled MCP-tab checkboxes were both invisible to grep-based design reviews because they're aesthetic / visual issues. HAT remains the irreplaceable last-mile control.
- **The orchestrator's "narrow-gate guidance" in implementing-agent prompts is a working pattern.** Once the SQLite WAL anomaly was logged, every subsequent leg's implementing Developer received the explicit narrow-gate fallback in the prompt and never re-encountered the hang. This style of dynamic prompt augmentation (orchestrator carries forward observed environmental quirks) is worth canonizing.

## Test Metrics Capture

Primary gate (`tests/test_design_tokens_a11y.py` + `tests/test_token_definitions.py` + `tests/test_oauth_provider_factory.py` + `tests/test_platform_tempdirs.py`): **56 passed, 0 failed, 0.95s in-container** (1.85s including `docker exec` ceremony). Zero flakes.

Broader gate (`pytest tests/ -x --ignore=tests/browser -k "not aiat"`): **hung — SIGTERM at 120s**. SQLite WAL anomaly persists post-Leg-05. Leg-05's diff (CSS + binary assets + flight artifacts) could not have introduced it; pre-existing environmental.

Pixel suite (`pytest -m pixel tests/browser/test_visual_snapshots.py`, no `--snapshot-update`): **10 passed, 2 failed, 25.06s**. The 2 failures are the documented `chat_with_messages` × dark + light Known Issue — `.session-agent-badge` resolves but stays empty (9× retries).

**Delta vs M04 F02 baseline (the prior debrief that audited the same testing surface)**:
- a11y suite grew from 40 to 45 parametrizations (3 new `accent_api` pairs in Leg 02 plus 2 from intervening missions). Sub-second timing held.
- Pixel suite baseline regen-pass rate degraded from 12/12 (M04 F02) to 10/12. The two failures are NOT a Mission-08 regression — pre-existing seeder bug surfaced because Mission 08 forced a regeneration. The M04 F02 debrief does not mention `chat_with_messages` issues; the bug landed silently between M04 F02 and now.
- Visual snapshot total disk usage: ~600KB region post-rebaseline. Still well under the 2MB Git-LFS threshold M04 F02 forecasted (and irrelevant since baselines are gitignored per user-global rule).

## Recommendations

1. **Establish three-dimensional pre-flight grep for any future brand / palette / vocabulary change.** Brand string + old palette hue + old palette code-name + hardcoded hex values. Inexpensive; catches the class of misses this flight saw at design review.
2. **Extract `.checkbox-primary` primitive to `components.css` before Flight 3 (Administration Polish) or Flight 4 (Studio Polish) starts.** The three per-area checkbox treatments are debt; one shared primitive consumed by the existing call sites prevents a fourth from emerging.
3. **Fix the `app_with_agent` Playwright fixture's `.session-agent-badge` populate path as part of Flight 5 (Chat Response Trace).** Flight 5 is the natural home — it touches the WebSocket / session-join / `_send_pause_snapshot_if_needed` code that the seeder exercises.
4. **Codify the three patterns identified by Architect** (dynamic `__version__` interpolation; `./scripts:/app/scripts:ro` bind-mount; `_ensure-playwright` post-rebuild requirement) in `agents.md` and `CLAUDE.md` at the next routine-maintenance pass. None warrant a flight; all are documentation lifts.
5. **Document the narrow-gate fallback in this project's flight-design template** (or as a `CLAUDE.md` Testing-section addendum) so future flights don't rediscover the SQLite WAL hang under time pressure. Independently, a routine-maintenance pass should address the underlying pytest-fixture isolation from the live daemon.

## Action Items

- [ ] **Open a maintenance pass to extract `.checkbox-primary` primitive** to `components.css` before Flight 3/4. Roughly 30-line lift from `studio.css:171-209` plus consumer call-site updates.
- [ ] **Fix `app_with_agent` Playwright fixture as part of Flight 5 design.** Track via mission Known Issue; add a leg under Flight 5 (or piggyback onto the chat trace persistence leg). Restores 12/12 pixel suite at flight-end.
- [ ] **Routine-maintenance follow-up: pytest isolation from live uvicorn DB.** Either (a) test fixtures spin up isolated DB connections, or (b) `make test` pauses the daemon's DB handle. Today the broad-gate run hangs indefinitely; this is now a known constraint that has blocked four flights' worth of broad-gate verification.
- [ ] **Codify three project-wide patterns**: `__version__` interpolation, scripts bind-mount, `_ensure-playwright` requirement. Single doc-only PR sized at maintenance-pass cadence.
- [ ] **Add a `# DO NOT DELETE — DEFAULT_SOURCE` marker (or equivalent test assertion) for `gleepglorp_icon.png`** in `static/brand/`. Cheap insurance against accidental deletion breaking `make brand-assets`.
- [ ] **Update flight-design template (or `agents.md`)** with the three-dimensional grep recommendation and the `grep -E '#[0-9a-f]{3,6}' tokens.css` hardcoded-hex enumeration for palette-touching flights.
- [ ] **Mission action item**: Flight 2 (Design Language: Robot/Control Panel) should retune `--accent-api` in the aesthetic context, not leave it as the recycled-cyan placeholder. Add to Flight 2 scope at design time.
- [ ] **Document the topbar mascot-icon CLS contract** in `agents.md` design-system section (one line: "topbar `<img>` requires explicit width/height + `flex-shrink: 0` to prevent layout shift on first paint").
