# Flight Log: Alignment

**Flight**: [Alignment](flight.md)

## Summary

**Status**: ready (planned 2026-10-06).

---

## Reconnaissance Report

**Sources:**
- the open squawks (0112–0116, 0119–0125);
- the Flight 3, 4 and 5 debriefs' carried items;
- the reference spec §13 and §15;
- the mission's SC1–SC10.

This is a read-only sweep of `main` at `aaee705` (v0.10.0) by a Sonnet agent, on 2026-10-06.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| 0112: creating a provider without `base_url` returns 500 | confirmed-live | `api.py` `create_provider`: `model_validate` with no `ValidationError` catch | A small fix (422) |
| 0113: the Tools tab category master toggle has no name | confirmed-live | `areas/studio/tools-tab.js:125-137` | A small fix (`aria-label`) |
| 0114: info-icon buttons are named only by `title` | confirmed-live | `provider-editor.js:227,262,285`, `tools-editor.js:174`, `tools-form-helpers.js:120`, `mcp-server-editor.js:901` | A small fix |
| 0115: the KB re-index-all test searches mid-reindex | confirmed-live | `test_flow_studio_knowledge_inventory.py:599-613` | A test-only fix |
| 0116: Settings tile title row and badge overlap | confirmed-live | `admin.css:142,155,156` | A mechanical fix (a flex title row), or an `App.ui` tile factory (scope decision) |
| 0119: a degraded join of the same id stays subscribed | confirmed-live | `app.py:2783`, `:2798-2802` | A small backend fix |
| 0120: a cancel before the turn starts sends no `cancelled` | confirmed-live | `app.py:3037-3041` | A small backend fix, or leave (a human click cannot hit the window) |
| 0121: the behavior crew file lacks the CDP recipe | confirmed-live | `.flightops/agent-crews/behavior-tests-execution.md` is unchanged since Flight 4 | A docs fix |
| 0122: the Flight 4 spec wording | confirmed-live | `jump-to-palette.md:92,94` still name `studio-description` as a testid | A docs fix |
| 0123: the `windows-window-chrome` wording | confirmed-live | only the leg 4 Revised line | A docs fix |
| 0124: the helper closure pin | confirmed-live | `windows_test_copy.py:2237`; no pin test | A small test, or leave |
| 0125: the pywebview 6.x blocker note | confirmed-live | no mention in `agents.md` or `pyproject.toml` | A docs fix |
| F4 B1: the faint Dark pending-row wash | needs-human-recheck | `components.css:683` | Operator decision |
| F4 B2: no focus ring on `rail-jump-to` after a pointer close | needs-human-recheck | `components.css:511`; the browser's `:focus-visible` heuristic | Operator decision, or retire |
| F4 B3: focus on `<main>` after Continue into a pending chat | confirmed-live (by design) | `nav.js:56-59,96` | Operator decision |
| F4 B4: message timestamps 1–4s off after a reload | needs-human-recheck | `message-bubble.js:106-120` | Investigate, or a squawk |
| F4 B5: UTC bubble times against local list times | confirmed-live | `message-bubble.js:106-114` against `chats-list.js:10-19` | Operator decision |
| F4 A4: the 1024 drawer overlay covers Send | already-satisfied (operator-accepted) | the Flight 4 debrief addendum | Retire |
| F4 A5: the unlabelled `#app-sidebar` | partially-satisfied | `router.js:573` labels it per destination; `index.html:27` is bare until the router runs | Wording only; fix or retire |
| F4: the deleted-agent heal for a restored `#chats/~new/{agent}` | partially-satisfied | `test_flow_chat_start_flow.py:417-444` covers an unknown agent, not a deleted one | Add one browser test |
| F3 Q7: focus drops to BODY after Create, Save and Test | confirmed-live | no post-save focus in `areas/studio/*` or `provider-editor.js` | Fix (a shared helper), or operator decision |
| F3: an `h1` at the Agents and Library roots | needs-human-recheck | not seen in the empty states | Check, then fix if missing |
| F5 D: window widths 640–1023 | confirmed-live (gap) | `base.css:56-58` "Below 1024px is unsupported"; no layout media queries; at 640 the main pane is 268px | Operator decision (enforce 1024, add a narrow layout, or accept), then a geometry test |
| F5 DD12: the five preview questions | needs-human-recheck | the preview artifact | Operator decision |
| SC9: the operator's packaged-build walk | needs-human-recheck | `windows-native-frame-splash` steps 11–19 | The operator walk |
| SC5 and SC9: Ctrl K in the installed WebView2 | needs-human-recheck | crew-verified at the Flight 5 close gate | The operator's confirmation |
| Reference spec §13 (D1–D5) | already-satisfied | pre-accepted; D5 decided at the Flight 3 checkpoint | Carry as accepted |
| Reference spec §15 (A1–A32) | partially-satisfied | owner flights 1–4; the statuses are recorded only in flight logs, not in the spec | Sweep the statuses into the spec at mission close |

**Mission criteria.**
- **SC1–SC7 and SC10** were delivered by Flights 1–5, with SC10's remaining items listed
  above (0113, 0114, F3 Q7, the root `h1`).
- **SC8** closes here: the operator's sample walk and the decision-sheet items.
- **SC9** closes here: the operator's packaged-build walk.

---

## Leg Progress

*(entries added as legs land)*

---

## Flight Director Notes

### Planning (2026-10-06)

- **The operator said "start flight 6"** after v0.10.0 shipped (PR #221 and the release
  PR #222 were merged by the Flight Director at the operator's instruction).
- **The reconnaissance** above came from a read-only sweep by a Sonnet agent.
- **The operator's answers** (crew interview, 2026-10-06):
  1. **Session:** "Fixes first, then walk".
  2. **The carried squawks:** "Fix them in this flight".
  3. **Windows:** "I already installed the version we just released, we can use that"
     (the walk uses the operator's installed v0.10.0).
  4. **Narrow widths:** "Show me first" (decided during the walk).
- **The flight spec** is written: nine design decisions and five legs. It goes to an
  Architect design review next.
- **Design review, cycle 1** (Architect, Opus): **approve with changes**. Three highs,
  six mediums and four lows. All were applied:
  - **DD2 narrowed:** in-place actions only. Closing actions keep Flight 3's DD8, and
    knowledge-base create keeps its folder-path focus (squawk 0101). The fallback is
    `.editor-title` with heading levels unchanged. The rule records the control when the
    action starts, lands after `nav.js`'s `setTimeout`, is guarded by `editorGen`, and
    replaces `keepFocus`/`hadFocus`.
  - **New DD11:** a visually hidden root `h1`, with `list-and-detail` step 2 re-authored
    in leg 1.
  - **DD4:** `fetchJson` error flattening; no input echo (the `api_key` leak); squawk 0081
    folded in (`create_chat_session`).
  - **DD5:** 0120's queued-task case, "at most one `cancelled`", and the browser check
    included or explicitly dropped.
  - **DD3:** wrapper elements in both builders, and the bounding-box tests.
  - **0114:** six sites.
  - **DD6:** the walk's operating rules (reachability, the mint host, hard reload versus
    restart, re-verifying by probe, 8485 is the operator's call), SC9 step 16 judged from
    the operator's recollection, and steps 17 and 19 operator-only.
  - **DD8:** three more contract specs.
  - **New DD12:** review and commit for each phase.
  - **SC8's evidence:** the Flight 3 and 4 probe records.
- **Answers to the review's questions** (Flight Director):
  1. The root `h1` is option (c), visually hidden (DD11).
  2. Knowledge-base create keeps its folder-path focus.
  3. Squawk 0081 is folded into leg 1.
  4. SC9 step 16 is judged from the operator's recollection.
  5. Inline walk fixes get a batched Reviewer pass before leg 4's commit.
- **No second cycle.** Leg 1 is HIGH risk and gets its own design review, which re-checks
  DD2 and DD11 against the code. That saves the waiting operator about 10 minutes.
- **Status: ready.**

---

## Decisions

- **2026-10-06, during planning: the provider Models list (DD10).**
  - **Reported:** "you can't select a model on the provider page" (an Anthropic and a
    Claude Max provider).
  - **Diagnosis:** the Models list is informational. It is unchanged since before
    Mission 25 (`areas/admin/provider-models.js` `renderBasicModels`), and models are
    picked per agent.
  - **The operator's choice:** "We probably just need a label that explains that one of
    the available models can be selected per agent."
  - It goes into leg 1 as a look-and-feel fix.

---

## Deviations

---

## Anomalies

---

## Session Notes
