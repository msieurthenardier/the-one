# Mission: UI Redesign — Clean, Professional, Consistent

**Status**: active

## Outcome

The entire web UI — Chat, Agent Studio, System/Administration, and the shared shell — reads as one calm, professional, trustworthy product. An operator can show the app in a work context without explanation or apology. The "alien console" visual language (glows, glass, bezels, chamfered panels, `// SECTION` terminal markers, pixel-font branding) is fully retired and replaced by a quiet, consistent design language where hierarchy comes from typography, spacing, and hairline borders rather than effects.

## Context

Mission 04 built the design-system substrate (tokens, `@layer` cascade, dual themes, Playwright net). Mission 08 layered the GleepGlorp brand and an intentionally weird "robot control panel" aesthetic on top: accent glows, glass surfaces, bezel shadows, brushed-metal chrome, chamfered panels, `// PREFIX` section markers, and a pixel-font wordmark. Missions 05–16 extended surfaces (tools admin, MCP, connectors, telemetry, thinking disclosure) within that language.

The operator now wants the opposite aesthetic: **clean, professional, and consistent** — the "quiet instrument panel" school (hierarchy via type/spacing/borders; one restrained accent; no decoration without meaning). This mission is a full visual-language replacement plus the UX-consistency and accessibility work needed to make the result feel like one product, not a re-skin of parts.

**Interpretation note (autonomous run)**: The operator's brief contained "I am not looking for a clean, professional and consistent experience," read as a typo for "**now** looking for" given the explicit contrast with the prior alien-console direction. All planning proceeds on that reading.

**Mission 16 status note**: M16's flights are all landed but the mission was never formally debriefed (`Status: active` at M17 planning time). Flagged for the operator; M17 proceeds per explicit operator directive.

## Success Criteria

- [ ] **SC1 — Complete visual-language replacement**: Every user-facing surface (shell, Chat, Studio, System, dialogs, toasts, empty states, design-gallery page) renders in the new design language; no surface retains glows, glass/backdrop blur, bezel/inset depth effects, chamfered panels, brushed-metal chrome, `//`-prefixed section markers, or pixel-font branding.
- [ ] **SC2 — Both themes individually designed and accessible**: Light and dark themes are each designed per-surface (not flipped), and every text/background token pair in both themes passes WCAG 2.1 AA contrast (automated audit covering ALL palette tokens, with any deliberate exceptions documented and annotated).
- [ ] **SC3 — One component vocabulary**: Buttons, form fields, dropdowns, tables/lists, cards, tabs, modals, toasts, badges, and empty states come from a single shared component vocabulary used identically across all three areas — no per-area variants of the same primitive.
- [ ] **SC4 — Modern chat experience**: Chat presents a focused reading layout with clear user/agent turn distinction, streaming output with a stop affordance and scroll-position awareness, legible markdown and code-block rendering, and tool-activity traces that stay out of the reading flow until expanded.
- [ ] **SC5 — Keyboard and assistive-tech operability**: All interactive elements on redesigned surfaces are keyboard-reachable and operable with visible focus; landmark/skip-link structure is preserved; prior accessibility investments (notably the M12 F4 connector-editor keyboard/ARIA fixes) survive the re-skin, re-verified via the existing behavior specs.
- [ ] **SC6 — Regression net intact and healthier than before**: The browser test suite passes with selectors migrated to the new markup; the five module-skipped browser test modules are re-enabled (or replaced with equivalent coverage) and no module-level skips remain; token-definition and contrast test suites pass.
- [ ] **SC7 — Behavior-verified core flows**: Witnessed behavior tests driven through a real browser apparatus pass for each area's core flow — a chat round-trip with streaming, an agent create/edit in Studio, and a provider configuration in System — in both light and dark themes.
- [ ] **SC8 — No performance regression**: UI performance stays within the established budget (heap-retention threshold under realistic load; no perceptible degradation in first-paint or interaction latency versus the pre-redesign baseline).
- [ ] **SC9 — Documentation reflects the new language**: The codebase design-system reference (`the_one/agents.md` design section), the living design-gallery page, and CLAUDE.md testing/design notes describe the new language, not the old one.

## Stakeholders

- **Operator (sole user)** — wants a UI they can use daily and show professionally; final acceptance authority (reviewing the mission branch after completion).
- **Future agent maintainers** — the codebase is maintained almost entirely by LLM agents; the design system must stay greppable, conventional, and documented so agents extend it without drift.

## Constraints

- **Branch discipline**: All work lands on the long-running branch `mission/17-ui-redesign`. No merge to main; the operator reviews the completed branch.
- **Brand continuity**: The product name (GleepGlorp AI) and violet accent family are retained; the mascot/wordmark may be simplified to fit the new language, but this is not a rebrand.
- **No frameworks, no build step**: The vanilla-JS `App`-namespace architecture, CSS custom-property tokens, and `@layer` cascade are retained (proven by M04/M08 to absorb full re-skins). No npm, no bundler, no server-side rendering shift.
- **Third-party policy — surgically loosened**: Zero-transitive-dependency, single-file, hash-pinned vendored libraries are permitted ONLY where correctness is adversarial (HTML sanitization, markdown parsing, optionally syntax highlighting), with a vendor manifest, CI integrity verification, and an XSS regression suite. Everything else stays hand-rolled. (Operator authorized loosening; scope kept minimal.)
  - **RESOLVED at Flight 4 — the loosening was NOT exercised (no library vendored).** The mission-planning premise (drawn from Flight-1 research) assumed the markdown renderer produced an untrusted HTML string that would need DOMPurify. The Flight-4 code survey found the opposite: `markdown.js` is already a DOM-building parser that NEVER uses `innerHTML` and never parses an untrusted HTML string — it emits DOM nodes via `createElement`/`textContent` with literal tag names and a fail-closed `safeHref()` scheme allowlist, making XSS impossible *by construction* rather than by filtering. An independent security-architect review confirmed that vendoring `marked`+`DOMPurify` would *worsen* posture (it forces an HTML-string→sanitize→fragment seam — reintroducing the very `innerHTML`-class operation the codebase deliberately eliminated — and breaks the streaming fragment/partial-buffer contract) for a CommonMark-completeness gain that is UI-polish, not an impediment. Per the operator's default (no third-party libs unless they clear the "impediment to a good UI" bar), the library did not clear it. **The mission's security intent is delivered structurally instead**: Flight 4 hardens `markdown.js`, adds the required XSS regression suite (expanded safeHref/mXSS-payloads-as-text boundary tests), and retargets the "CI integrity verification" from vendored-file hash-pinning to a **no-HTML-string invariant guard** (assert `markdown.js` innerHTML count stays 0; `render()` returns a `DocumentFragment`; tag names stay literal). Syntax highlighting deferred (see Open Questions). Decision + rationale recorded in Flight 4's flight log.
- **Test-stability contract**: Load-bearing elements carry stable `data-testid` attributes; a testid registry is established before markup churn begins.
- **Accessibility is a per-leg gate**, not a cleanup phase — every leg introducing or restyling interactive elements includes keyboard/ARIA/contrast acceptance criteria.
- **Dual themes are first-class**: every visual change is designed and verified in both themes ("land dark, port light" cadence permitted within a flight, but a flight doesn't land with one theme unfinished).

## Environment Requirements

- Local dev server via `make up` / `make restart` (no hot reload — restart after source edits). **M17 note (discovered F2 L1)**: port 8484 is squatted by the operator's production packaged app (`the-one-app.exe`) — never kill/mutate it; the mission dev instance runs `THE_ONE_PORT=8485 make up`, and ALL mission visual verification + behavior tests target `http://127.0.0.1:8485`.
- Playwright browser tests host-native via `make test-browser` (`scripts/run-tests.sh`).
- Behavior tests require: a running instance of the BRANCH build (mission dev instance on 8485 — see note above), browser apparatus (goldfinch MCP) live, mock provider available via `THE_ONE_DEV_MODE=true` for deterministic chat flows.
- Visual snapshot baselines are local-only (gitignored); regenerate per checkout.

## Open Questions

- [ ] Does the design-gallery (dev-mode) page get redesigned in place or rebuilt from the new component vocabulary? (Resolve in the tokens/components flight.)
- [ ] Custom dropdown widget vs. minimally-styled native `<select>` — commit one way during the shared-components flight (M07/M08 left this open).
- [x] Does syntax highlighting ship in this mission (vendored highlight.js custom build) or defer? → **DEFERRED** (Flight 4). Vendoring highlight.js would be a second (larger) supply-chain entry, must run after any sanitizer (ordering constraint), interacts awkwardly with the incremental streaming render, and doubles the code-block CSS surface (dual-theme). Given the mission's no-vendor resolution above and that highlighting is UI-polish not an impediment, it is deferred. The renderer already emits a `class="language-{lang}"` hook on code blocks, so shipping highlighting later is non-breaking.

## Design Decisions (mission-level, from viability review)

**JS/CSS lint gate**: The lint gate is confirmed Python-only (ruff); real JS/CSS linters are npm-delivered. Decision: **no npm even for dev tooling** — the supply-chain posture wins. Flight 1 instead ships hand-rolled grep-based CI guards (testid registry check, innerHTML-sink guard, banned-token guard after Flight 2) and documents the linter gap.
- Rationale: npm dev-dependencies execute arbitrary code on the build machine; that risk is the exact thing the project's policy exists to avoid, and grep guards cover the highest-value invariants.
- Trade-off: no general JS style enforcement; conventions doc + code review carry that load.

**Already-fixed items removed from scope** (architect verification, 2026-07-03): connector-editor A1–A4 fixed in M12 F4 (`connector-editor.js:2466-2891`); agent-editor `enabled_tools`/MCP decoupling fixed in M16 F9 L6 (backend); chat stop button exists (`chat.js:168`, `data-testid="chat-stop-btn"`). Flights treat these as **preserve-through-re-skin** obligations, not net-new work.

**M07 F10 relabel re-scoped**: the agent-editor tab already reads "Built-in Tools"; what remains is lazy-discovery semantic labeling ("tools the agent can load" vs "has loaded"). The label copy fix rides Flight 5; a chat-time loaded-set indicator is new functionality and stays OUT of this mission.

**Fresh performance baseline**: M08-era heap numbers predate M10–M16 UI growth. Flight 1 captures a fresh `App.perf` heap/interaction baseline on the pre-redesign branch point as SC8's comparison anchor.

**Markdown pipeline facade**: the `App.markdown` public API (parse/render) is preserved when internals are swapped to the vendored renderer/sanitizer; consumers (chat, gallery) don't change call sites.

## Known Issues

*(populated during execution as flights surface problems)*

- **`make restart`/`verify-serving` false-success when a foreign server holds the port** (found F2 L1, 2026-07-03): the repo server dies on bind while `verify-serving` gets 200s from the squatting process (here: the operator's packaged app on 8484), so `make restart` reports success without serving the new code. Fix (F2 Leg 3): assert port ownership (PID in `.the-one.pid` owns the bound socket) or a served-instance identity echo, so a foreign responder fails the check loudly.

- **Dead selector `connector-test-status`** (found by Flight 1 Leg 1 guard bootstrap, 2026-07-03; **RESOLVED by Flight 3 Leg 3**, 2026-07-03): `connector-editor.js` queried `[data-testid="connector-test-status"]` but no element defined that testid — the element was removed by M16 F5 L6 HAT round-7; both uses were null-guarded dormant dead code. Dispositioned in Flight 1 as an explicit allowlist entry (`KNOWN_DEAD_SELECTORS`) in `tests/test_ui_guards.py`. Flight 3 Leg 3 (cta-unification, studio cleanup bundle) removed the dead queries, the null-guarded `statusEl` blocks, and the allowlist entry together — `KNOWN_DEAD_SELECTORS` is now empty.

- **State-split, icon-only "New entity" CTA — discoverability/a11y concern** (root-caused by Flight 1 Leg 2, 2026-07-03; **RESOLVED by Flight 3 Leg 3** (cta-unification), 2026-07-03; touched SC5): the create affordance for entity grids (Agents, LLM Providers, MCP Servers, Connectors) moved between two different buttons depending on grid state, and the header CTA at rest was icon-only with a hover/focus-reveal label — no single stable target. Flight 3 Leg 3 unified it: one always-visible header CTA per entity grid (vocabulary `.btn-outlined-primary`, icon + text label, `data-testid="new-{entity}-btn"`) in both empty and populated states; the hover-reveal and `display:none` state-split rules were deleted; the empty canvas keeps an inviting duplicate (same component class + handler, no testid); the four `-empty` testids retired (registry rows pruned); all six consumer test files migrated to the unified contract (`test_flow_agent_crud.py`, `test_flow_provider_setup.py`, `test_flow_provider_grid.py`, `test_flow_studio_openrouter_picker.py`, `test_flow_studio_connector_navigation.py`, `test_flow_studio_mcp_navigation.py`).

- **Theme sync propagates set but not unset across tabs** (found by the shell-navigation-smoke behavior-test run, 2026-07-03; assign to **Flight 2** theme/token work): with two same-origin tabs open, selecting an explicit theme in one tab live-updates the other, but restoring "Auto" (which *removes* the `theme-preference` localStorage key) does not — the second tab keeps the stale in-memory theme until reload. Likely the `storage`-event handler ignores key-removal events (`newValue === null`). Cosmetic for a single-tab user; real for multi-window use (the desktop shell makes that plausible). Evidence chain in `tests/behavior/shell-navigation-smoke/runs/2026-07-03-16-26-39.md`.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: **Regression-net foundation** — testid registry + CI grep guards, re-enable/replace the five module-skipped browser tests (timeboxed root-cause on the two unexplained hangs; those two may defer re-enable until after Flight 3 with SC6 as the mission-end gate), fresh `App.perf` heap/interaction baseline capture, baseline behavior-test spec for the pre-redesign app.
- [x] Flight 2: **Design language v3 — tokens and type** — new token tables for both themes (quiet-instrument-panel palette, spacing/radius/shadow system, motion), retire glow/glass/bezel/chamfer/chrome tokens, focus system, full-palette contrast test parametrization, fonts/type-scale updates.
- [x] Flight 3: **Shell and shared components** — topbar/sidebar/nav restyle, clean wordmark treatment, shared primitives (buttons, fields, dropdown decision, tables, cards, tabs, modal, toast, empty-state) rebuilt in the new language, design-gallery updated as the living reference.
- [x] Flight 4: **Chat re-skin** — reading layout, composer, streaming/stop affordances, scroll behavior, tool-trace and thinking disclosures, markdown pipeline hardening (vendored sanitizer/renderer + vendor-integrity infrastructure + XSS suite). *(Landed 2026-07-05. No-vendor reversal — the security intent delivered structurally via parser hardening + no-HTML-string invariant guard + XSS suite instead of a vendored sanitizer; see Third-party constraint above + Flight 4 flight log.)*
- [ ] Flight 5: **Studio re-skin** — agents/knowledge/MCP/connectors surfaces in the new language; M12 F4 connector-editor a11y fixes preserved and re-verified (existing behavior spec); lazy-discovery label copy corrected (re-scoped M07 F10 remainder).
- [ ] Flight 6: **System re-skin** — general/providers/built-in-tools surfaces, provider and tool editors, admin forms and tables in the new language.
- [ ] Flight 7: **Hardening and verification** — cross-area consistency sweep, a11y audit, performance audit against budget, behavior-test suite for core flows in both themes, documentation updates (agents.md, CLAUDE.md, README screenshots if any).
