# Flight Debrief: Filesystem Expansion & Constraints

**Date**: 2026-04-29
**Flight**: [Filesystem Expansion & Constraints](flight.md)
**Status**: landed
**Duration**: 2026-04-29 (single session, ~8 hours of orchestrated execution)
**Legs Completed**: 8 of 8 (L1, L2a, L2b, L3, L4, L5, L6, L7-HAT, L8)

## Outcome Assessment

### Objectives Achieved

Flight 3 delivered the full F3 scope as specified:

- **9 filesystem tools** registered: `read_file`, `write_file`, `edit_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `grep`, `list_dir`. 6 are new; 3 were migrated from `_EmptyConfig` to `FilesystemConfig`.
- **Resolver expanded** with `NarrowPrefix` and `NarrowSuperset` sentinel markers (4-marker mutual exclusion enforced).
- **Four constraint types** enforced via the per-category `FilesystemConfig`: path allowlist (NarrowPrefix), path denylist (NarrowSuperset), read-size cap (Narrow + ui_hint dropdown metadata), binary-file allow flag (Narrow, positively-named).
- **`ConstraintError` exception type** introduced; tool wrappers format `[error] [constraint] {msg}` to distinguish policy refusals from environmental failures.
- **3 module-level check helpers** with documented strictness gradient: `_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path` (the third was added retroactively in L3).
- **HAT validated** against Qwen 2.5:7b (small-model target) with 5/7 PASS clean; 2 small-model agency artifacts captured as mission Known Issues; Haiku 4.5 re-verification confirmed F3 error strings are model-agnostic correct.
- **Tests**: +75 new (18 filesystem_config + 32 filesystem_helpers + ~28 tool tests + ~17 resolver/marker tests). 646 unit tests pass; 220 browser tests pass; lint clean across F3-touched files.
- **Documentation**: `agents.md` Test Conventions section; `tests/CONVENTIONS.md`; `CLAUDE.md` Resolver semantics + Filesystem constraint surface sections refreshed; mission Known Issues filed.

Single commit `88a24a7` (24 files, +8405/-94). PR #21 (draft).

### Mission Criteria Advanced

This flight contributed to four Mission 05 success criteria:

- ✅ **Filesystem tooling supports the full lifecycle** — read, write, in-place edit, delete, move, directory creation, pattern-based file discovery, and content search. (F3 ships the full surface.)
- ✅ **Each tool category enforces tool-level constraints** with per-agent narrowing through a single resolution layer — partially met (F3 introduces the first real values: path scope + read-size cap + binary refusal). F4 and F5 will add timeout caps, output caps, and URL/host scope on the same seam.
- ✅ **Each kept tool has automated coverage** under happy-path AND constraint-violation use — F3 covers the filesystem subset (path-scope rejections, denylist hits, size-cap exceeded, binary-file refusals, symlink-escape detection).
- ✅ **Filesystem and execution tooling architected for cross-platform support** — F3 routes all filesystem tools through `the_one/platform/` (canonicalize, is_within); no tool re-introduces inline `Path.expanduser().resolve()`.

## What Went Well

**Architecture choices validated by execution.** Decision 1's pivot from `Substitute + model_validator(mode="after")` to first-class `NarrowPrefix`/`NarrowSuperset` sentinel markers held up cleanly — the resolver remains the single audit point, and the mutual-exclusion enforcement is a quiet correctness win that the original Substitute path could not have provided. Decision 2's per-category `FilesystemConfig` is validated by the symmetry at every tool's call site (`cfg = self._config; canonical = _filesystem_check(path, cfg)`). Decision 10's scope-first ordering in `_filesystem_check_write_parent` (filesystem.py:170-178) is the most architecturally interesting choice — it prevents a hostile prompt from learning whether out-of-scope paths exist, and the test `test_out_of_scope_missing_parent_prefers_constraint_over_filenotfound` locks the invariant.

**HAT proved its value as a design-completion gate.** Decision 6 promoted HAT from optional to required for flights with user-visible constraint behavior. F3's HAT against Qwen 2.5:7b found that:
- Step 4's binary-refusal wording was misread by the model as a passable parameter (`allow_binary_files=true`); a tighter phrase (`set by operator only; not an agent-passable parameter`) fixed it cleanly.
- Steps 3 and 6 surfaced small-model agency limits — failures that no unit test would have caught and no wording fix could fully cure (validated by Haiku 4.5 re-verification).

This separation between *clarity* (wording can fix) and *agency* (model capability floor) is the highest-leverage finding of the flight.

**Two-clause try/except envelope.** Every tool wraps `try: ... except ConstraintError as e: return f"[error] [constraint] {e}" except Exception as e: return f"[error] {e}"`. Repeated 9 times in `filesystem.py`; F4/F5 will repeat it. This is a load-bearing convention that should be lifted to a documented "tool authorship contract" before F4 introduces the second consumer.

**PrivateAttr + model_post_init caching invariant.** `FilesystemConfig` eagerly canonicalizes allowlist/denylist entries once at construction (filesystem.py:94-101). The `TestCachingInvariant` test (mock-counter pattern) asserts a *performance* contract, not just behavior — this is a reusable template for future Configs.

**Per-leg design-review cycle caught real issues.** L1 round 1 caught two high-severity items (a silent test-substring break and exception-class drift); L3 caught the missing helper variant before implementation. The 2-cycle cap was sufficient for every leg.

## What Could Be Improved

### Process

- **Helper-set strictness gradient must be specified up front.** L3's retroactive `_filesystem_check_write_path` is the canonical example: L2b shipped `_filesystem_check_write_parent` (existence-checking) but `WriteFileTool`'s auto-create-parents contract needs the no-existence-check variant. The L3 design developer paused, evaluated three options, and picked extraction — correct outcome, but it should have been picked at L2b design time. **Methodology fix:** when designing helper sets, the leg spec must enumerate the strictness gradient (must-exist / may-exist / must-not-exist) AND the {context-of-use, helper-needed} pairs across the entire flight, not just the next leg's needs.

- **Test-count miscounts (twice).** L2b's leg spec claimed ~22 tests when the breakdown summed to 26; L3 claimed 8 new but listed 7. Both were prose-vs-AC arithmetic drift, caught by reviewers post-hoc, not pre-design. **Fix:** add an "AC tests-claimed must equal spec body sum" check to the leg-design template.

- **Helper-code lint pass before AC is finalized.** `_format_edit_preview` was specified with a function-local `CONTEXT = 3` constant; ruff N806 forced module-level promotion mid-implementation. A lint pass on helper code blocks at design time would have caught this.

### Technical

- **Three near-identical write-side helpers** (`_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path`) form an implicit strictness gradient. Callers must pick correctly; nothing structurally prevents misuse. **Refactor opportunity:** unify behind one signature with explicit kwargs (`leaf_must_exist=False, parent_must_exist=False`) so the strictness level is declared at the call site.

- **Per-match `_filesystem_check` in `glob`/`grep`** is correct but expensive on large trees. No cap on tree size; no profile data. Acceptable for typical agent workloads but undocumented as a complexity concern. **Refactor opportunity:** extract `_walk_with_scope_check(root, pattern, cfg)` shared between `glob` and `grep` — they already duplicate the per-match-skip pattern with slightly different counters. F4 file-walking code can reuse it.

- **`ListDirTool` does NOT filter denylisted descendants.** The flight log calls this out explicitly ("listing reveals existence, but `read_file` blocks access"), but no test locks current behavior. A future change could regress silently. **Action:** add a regression test asserting `list_dir` of `~` shows `.ssh` / `.aws` etc. in the listing (and `read_file` blocks access to them).

- **`grep`'s in-loop `_check_read_size` + `_is_binary` + `read_text`** does three passes through the file head per match candidate. Acceptable; flag for future optimization only if profiles show it.

### Documentation

- **`[error] [constraint] {msg}` formatting contract is not documented in `agents.md`.** It's a load-bearing convention now, repeated 9 times in `filesystem.py` and ready for F4/F5 to inherit. Add a "Tool authorship contract" section to `agents.md` before F4.

- **F3 threat model is in `flight.md` (Decision 10) but not in `agents.md` or `CLAUDE.md`.** "Operator-trusted setup, NOT malicious filesystem actor" should be a single canonical statement that F4/F5 inherit by reference.

- **Operator/agent split for `allow_binary_files` is only in the error message wording.** Agents reading their own system prompt won't know `allow_binary_files` is operator-only without hitting the error first. Should be in `agents.md`'s tool description if it isn't already.

- **Mission Known Issues #1 and #2** (Qwen agency limits) deserve a forward-link from `CLAUDE.md`'s constraint section: "constraint messages describe the constraint, NOT the recovery — see Mission Known Issues for evidence of why."

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L3 added `_filesystem_check_write_path` (not in L2b spec) | L2b's helper set was incomplete; auto-create-parents contract requires no-existence-check variant | **Yes** — promote "design helper sets against the strictness matrix up front" to methodology |
| L3 dropped the "use offset/limit to paginate" hint from `_check_read_size` | Today's `read_file` reads-then-slices; the hint was misleading | Keep as one-time fix; locked by the `"exceeds cap"` substring |
| L7 wording iteration (size-cap "operator can raise" hint, binary "set by operator only") | HAT against Qwen 2.5:7b revealed Step 4 misread; Step 3/6 needed sharper language | **Yes** — promote "HAT-driven wording iteration is a Director judgment call, not a mechanical fix" |
| L7 reverted `; re-read the file if you need the surrounding lines` | Caused agent to fabricate synthetic context (active misinformation worse than punt-to-user) | **Yes** — wording fixes can over-prescribe model behavior; treat HAT as signal, not pass-fail |
| `_format_edit_preview` `CONTEXT` hoisted to module-level constant | ruff N806 flagged the function-local UPPERCASE | One-off; consider module-scope-by-default for tuning constants |
| Container source-vs-installed-package double-sync (every leg) | `the-one` runs from `Dockerfile COPY` source AND `/usr/local/lib/.../site-packages/`; tests must see both | **Yes** — fix in routine maintenance; bind-mount or `pip install -e .` would eliminate ~10 minutes per leg |

## Key Learnings

1. **"Small-model friendly" conflates two distinct properties.** HAT proved that error-string wording is sufficient for *comprehensibility* (the agent can read what the constraint says — Step 4 fixed cleanly with sharper wording) but cannot resolve *autonomous recovery* (multi-step tool-chain reasoning — Steps 3/6 failed regardless of wording on Qwen 2.5:7b; Haiku 4.5 passed both with the same shipped strings). Future flights should target comprehensibility in error strings; recovery is a model+prompt concern with a capability floor.

2. **HAT-driven wording iteration is a Director judgment call.** The L7 re-run showed `; re-read the file if you need the surrounding lines` *regressed* Step 6 from a graceful punt-to-user to active misinformation. Wording fixes can over-prescribe model behavior. Future flights should treat HAT as a signal source, not a pass-fail gate that requires inline rewording.

3. **Information-leak prevention generalizes.** Decision 10's scope-first ordering rule (check policy before existence/availability) is not filesystem-specific. F4 timeouts ("not in budget" before "process not found") and F5 SSRF ("blocked host" before "host unreachable") should adopt the same envelope.

4. **HAT and unit tests cover orthogonal axes.** Unit tests prove the code raises `ConstraintError` with the right message shape; HAT proves a real LLM can recover from the message. Neither replaces the other. F4/F5 should plan both.

5. **Helper architecture is the design surface most prone to incomplete specification.** Pydantic schemas, marker semantics, and tool surfaces were specified well; helper sets were under-specified twice (L2b → L3 retroactive add). Promote helper-set design to a first-class flight-design step.

## Recommendations

1. **(Critical) Promote `ConstraintError` and the two-clause try/except envelope** to a documented "Tool authorship contract" in `agents.md` before F4 starts. Consider extracting `ConstraintError` from `the_one/tools/filesystem.py` to `the_one/tools/_constraint.py` (or `base.py`) so F4/F5 import rather than redefine.

2. **(Critical) Refine the mission "small-model friendly" constraint** to distinguish comprehensibility from autonomous recovery. Carry to mission debrief; F4/F5 leg specs should target comprehensibility for error strings and document recovery-pattern expectations separately.

3. **(Important) Specify helper sets against a strictness gradient at flight-design time.** Add a leg-design template field: "Helpers introduced (with {strictness, context-of-use} matrix)." F4 will face this with PTY/non-PTY/timeout-budget variants; F5 with redirect-following variants.

4. **(Important) Unify the three `_filesystem_check_*` helpers** behind one signature with explicit kwargs (`leaf_must_exist`, `parent_must_exist`). Documents the strictness gradient at the call site; low-risk refactor; high readability win for F4/F5 helper authors who will inherit the pattern.

5. **(Important) Fix the container source-vs-installed-package sync friction** as a routine-maintenance pass before F4 starts. Either `pip install -e .` in the dev image OR bind-mount `the_one/` into `/app/` and `/usr/local/lib/.../site-packages/`. Roughly 10 minutes per leg of `docker cp` invocations would disappear.

6. **(Important) Promote the `ui_hint`/`ui_choices` Pydantic-schema convention to a documented standard** in `agents.md` (it's mentioned but not fully formalized). F4 should reuse for `timeout_seconds` choices; F5 for `redirect_cap` choices; F6 form-generator should consume.

7. **(Important) Add an `AC.tests-claimed` lint rule** to the leg-design skill: count claimed new tests in the AC bullets and assert it matches the sum from the test plan body. Caught manually 2×; trivial to mechanize.

8. **(Minor) Add a regression test for `list_dir` not filtering denylisted descendants.** Lock the current "listing reveals; access blocked" behavior so a future change cannot regress silently.

9. **(Minor) Document the F3 threat model** ("operator-trusted setup, NOT malicious filesystem actor") once in `agents.md` or `CLAUDE.md` so F4/F5 inherit by reference.

10. **(Minor) Forward-reference the Mission Known Issues** from `CLAUDE.md`'s constraint section: "see Mission Known Issues for evidence of why constraint messages describe the constraint, not the recovery."

## Action Items

- [ ] Promote `ConstraintError` to a shared module before F4 begins; document the envelope in `agents.md`
- [ ] Refine the mission "small-model friendly" constraint at the mission debrief
- [ ] Add helper-set strictness-gradient field to leg-design template (`mission-control` skill repo)
- [ ] Unify `_filesystem_check_*` helpers in a small refactor before F4 (or as F4-L1)
- [ ] Fix container source-vs-installed-package sync (routine maintenance task)
- [ ] Standardize `ui_hint`/`ui_choices` convention in `agents.md`
- [ ] Add `AC.tests-claimed` consistency check to `/leg` skill
- [ ] Add `list_dir` denylist-listing regression test
- [ ] Document F3 threat model in `agents.md` / `CLAUDE.md`
