# Flight Debrief: Pairing peers-axis decoupling (account-scope peers → DM-only)

**Date**: 2026-06-02
**Flight**: [Pairing peers-axis decoupling](flight.md)
**Status**: landed
**Duration**: 2026-06-02 (single session — planning, 2-leg execution, review, land)
**Legs Completed**: 2 of 2

## Outcome Assessment

### Objectives Achieved

The flight achieved its objective in full. The account-scope `allowlist.peers` axis now gates **DMs only** — the account-scope peers block was removed from `_admits_inbound_guild` (`the_one/connectors/_acl.py`), so guild-channel admission is gated by the account-scope `channels`/`guilds`/`roles` axes plus the per-agent overlay alone. The DM path's peers gating (`_admits_inbound_dm`), the per-agent `connector_acls.peers` routing overlay (F15 L4), and the deliberate two-step DM grant (approve endpoint untouched, still appends `dm_allowed=False`) are all preserved — verified byte-unchanged in code and green throughout the suite.

The change is surgical: a 9-line block deletion plus a load-bearing replacement comment, a complete 4-site docstring sweep, five unit-test assertions (inverted/added), one converted command test, the `agents.md` doc carve-outs, the mission Known Issue closure, and a credentials-gated `discord_hat` reproduce-gate.

### Mission Criteria Advanced

- **Closes the F15 L7 mission Known Issue** — "Pairing-approval collapses the open peers axis → connector locked to one peer." This was the flight's sole contributing criterion and it is resolved (marked `[x]` in `mission.md` with fix evidence + F9/F10/F12 lineage).
- **Hardening prerequisite for criterion #19 (full-working-day daily-driver run, F17)** — without this fix, approving one unknown DM-er during a working day would silently lock the bot to that single peer everywhere. The F17 gate can now proceed.

All flight checkpoints (L1 + L2) were met. The binding gate — the `tests/test_connectors_acl.py` RED-before/GREEN-after matrix — passed.

## What Went Well

- **The design-review gate did its job — twice.** Both legs entered design with a latent error that review caught before implementation, so neither implement leg hit a surprise. L1 review found a guild-context test the recon missed (`test_connectors_commands.py::test_account_allowlist_denies_peer`); L2 review caught a wrong-edit hazard (the `two-symmetric-paths-in-acl` enumeration is per-agent-scoped — rewriting it to "account peers DM-only" would have been incorrect). Front-loading these into design, not implementation, is exactly the intended value of the per-leg review.
- **Root-cause fix, not symptom patch.** The F15 L7 lock-out was the consequence of the account-scope peers axis never being formally demoted to DM-only despite F9/F10/F12 collectively creating that intent. F16 removes the actual anomaly (the guild path consulting the wrong axis), restoring a coherent single-responsibility story for guild admission.
- **Load-bearing documentation done right.** The deletion site carries a 4-line explanatory comment (so a future reader doesn't mistake the gap for an accidental deletion); the new `account-scope-peers-is-DM-only` convention names the account-vs-per-agent asymmetry as permanent/intended with full lineage; the five-axes statement + header were *restructured* (not caveated); and the `two-symmetric-paths-in-acl` per-agent enumeration was correctly left intact with only a scope-divergence note.
- **Strong test assertions.** The asymmetry-interaction test pins the *per-agent* deny reason AND asserts the *account-axis* reason is absent — it cannot pass if an account-scope peers check is ever reintroduced. The channels-boundary test uses the specific channel reason string, so a vacuous-admit regression would fail it.
- **Clean metrics, no regression** (see Technical).

## What Could Be Improved

### Process

- **The recon's "Architect-verified none" claim was scoped too narrowly.** The flight stated "No tests in `test_connectors_routing.py`/`test_connectors_inbound.py` pin account-peers-gates-guild — Architect-verified." That is true *as stated* but incomplete: `test_connectors_commands.py::test_account_allowlist_denies_peer` is a behavioral test (does the command dispatcher respect the account allowlist?) that exercises the ACL via a guild-context envelope, and it was not in the two files checked. The reviewer caught it by reasoning about what *any* guild-context peers-deny test would mean — not by a systematic search. The fix (operator-confirmed disposition: codify) is a recon heuristic: **for any ACL admission-condition removal, grep the whole test corpus for the reason string the condition emits** (here, `"is not admitted on account"`), not just the variable reads — a reason-string grep catches behavioral tests in non-ACL files that a variable-read grep misses. See Action Items.

### Technical

- **Test metrics (this run): 2835 passed, 4 skipped, 529 deselected, 3 warnings, ~286s wall.** Comparison to priors:

  | Flight | Passed | Skipped | Deselected | Wall (s) |
  |--------|--------|---------|------------|----------|
  | F13 | 2796 | 4 | 520 | 243 |
  | F14 | 2820 | 4 | — | 301 |
  | F15 | 2832 | 4 | 528 | 262 |
  | **F16** | **2835** | **4** | **529** | **286** |

  **+3 passed** vs F15 — consistent with the test additions (3 new ACL tests + 1 inverted + 1 extended-equivalence in `test_connectors_acl.py`; the command test was a context change, not a net-new function). **+1 deselected** — the new `discord_hat`-marked `test_pairing_peers_decoupling.py`. **+24s wall** is within historical run-to-run variance (F14 ran 301s; F15 was 39s faster than F14) — the added tests are pure-logic and run in ~0.08s for the full 99-test ACL suite, so they cannot account for the delta; it is teardown/async noise, **not a regression**. The **3 warnings are the pre-existing `aiosqlite` event-loop-closed teardown** `PytestUnhandledThreadExceptionWarning`s (a tracked mission Known Issue), unchanged by F16.

- **Low-risk untested precedence:** the DM path under `dm_admission="all"` mode with a *non-listed* account peer denies (the peers gate short-circuits before the `dm_admission` branch). The code is correct, but the `TestDmAdmissionCompositionMatrix` doesn't machine-pin this specific cell. A documentation-by-test opportunity, not a defect.

- **Cosmetic:** the `_admits_inbound_guild` docstring has a slightly awkward sentence break left over from removing the peers paragraph above the structured-tuple paragraph. Worth a cleanup pass next time that docstring is touched.

### Documentation

- **The `tests/live/discord_hat/` README gap (carried from F15) is still open.** F16 added a new scenario file (`test_pairing_peers_decoupling.py`) but there is still no provisioning/run-instructions/timing-rationale README for the HAT driver suite. This should land before F17's daily-driver run, which is the first full operator exercise of the driver suite.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L1 implementing agent truncated mid-run before emitting `[HANDOFF:review-needed]` / writing its flight-log entry | Agent hit a turn/token boundary after the code+tests landed on disk | No — FD-side recovery (verify on-disk against every AC + run suites to green + complete bookkeeping) is the correct contingency; the work was complete and verified |
| Flight-end Reviewer spawned as Sonnet rather than the crew-default Haiku | FD judgment: correctness-critical ACL semantics warranted a stronger reviewer; within the "never Opus for Reviewer" envelope | Situational — escalating the Reviewer model for subtle-correctness flights is a reasonable FD call; not a blanket change |
| L2 reproduce-gate committed but never executed live | No operator-logged-in Discord session in an autonomous flight; flight explicitly allowed unit-only with the gate as a committed artifact | Yes (already the flight's documented Acceptable Variation) — ships as a re-runnable regression sentinel for F17 |

## Key Learnings

- **Removing an ACL condition is a behavioral change with a non-local test footprint.** The condition's *reason string* is the most complete coverage signal — behavioral tests in command/routing/dispatcher files can depend on an admission deny without ever importing `_acl` or asserting the reason text. Variable-read recon under-counts; reason-string recon catches them.
- **Same-named axes across scopes are a standing confusion hazard.** `allowlist.peers` (account-scope, `{id, dm_allowed}`, now DM-only) and `connector_acls[…].peers` (per-agent, `{id}`, guild-routing-narrowing) share a key but diverge in shape, semantics, and path-scope. The mitigation that works is explicit: a load-bearing deletion comment + a named convention stating the asymmetry is permanent. Reasoning-by-symmetry from the per-agent block is the specific trap.
- **Convention entries should state path-scope, not just tri-state.** F16's amendment to `per-axis-tri-state-override` established the precedent that an axis is "guild-only," "DM-only," or "both-paths." Future axis additions should declare this rather than silently inheriting an "all axes apply to all paths" assumption.
- **F16 closes the mechanical lock-out but not the approve-flow UX gap.** An approved peer gets guild access immediately yet cannot DM until the operator flips a second toggle, with no UX signal. This is intentional (two-step preserved) and correctly out of F16 scope. Operator disposition: **park until F17 evidence** — the daily-driver run is the trigger; if an approved peer's DM silently fails and confuses, that signals a focused follow-on UX/docs flight against the approve flow.

## Recommendations

1. **Codify the ACL-removal recon heuristic in `agents.md`** (operator-confirmed). Add a named convention so the next ACL-touching flight inherits it mechanically. Turnkey text proposed in Action Items.
2. **Write `tests/live/discord_hat/README.md` before F17** — provisioning, env vars, run commands, the `@mention`/timing rationale, and the catalogue of committed scenarios (now including `test_pairing_peers_decoupling.py`). Carried from F15; F17 is the forcing function.
3. **Keep the pairing-approval `dm_allowed=False` Known Issue open and visible** until F17 produces evidence; do not scope a follow-on pre-emptively (operator-confirmed: park).
4. **In the next ACL-touching flight, fold in two low-cost cleanups:** the `_admits_inbound_guild` docstring sentence-break tidy, and a `TestDmAdmissionCompositionMatrix` cell pinning `peers=["P1"] + dm_admission="all" + non-listed peer → deny` (makes the short-circuit precedence machine-verified).

## Action Items

- [x] **Codify `acl-removal-recon-greps-reason-strings` in `the_one/agents.md`** — done in the post-debrief doc commit (added after `two-symmetric-paths-in-acl`). Proposed entry (as landed):
  > **`acl-removal-recon-greps-reason-strings`** — When recon plans removing or weakening an ACL admission condition in `the_one/connectors/_acl.py`, grep the ENTIRE test corpus for the *reason string* that condition emits (e.g. `"is not admitted on account"`), not just for reads of the condition's variables. Behavioral tests in non-ACL files (`tests/test_connectors_commands.py`, `_routing`, `_inbound`) can depend on an admission deny — asserting `_permitted_agents(ctx) == []` or a dispatcher outcome — without importing `_acl` or asserting the reason text, so a variable-read grep misses them. Citation: F16 L1 recon scoped "Architect-verified none" to `test_connectors_routing.py`/`test_connectors_inbound.py` and missed `test_connectors_commands.py::test_account_allowlist_denies_peer` (a guild-context account-peers-deny test); design review caught it before implementation, but a reason-string grep at recon would have found it mechanically.
- [ ] **Author `tests/live/discord_hat/README.md`** before the F17 daily-driver run (carried from F15 debrief).
- [ ] *(Deferred — park)* Re-evaluate the pairing-approval two-step DM-grant UX gap after F17 surfaces daily-driver evidence; scope a follow-on only if confusion is observed.
- [ ] *(Low priority, fold into next ACL flight)* `_admits_inbound_guild` docstring sentence-break tidy + the `dm_admission="all"` + non-listed-peer precedence test.
