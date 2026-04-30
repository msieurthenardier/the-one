# Flight: Filesystem Expansion & Constraints

**Status**: landed
**Mission**: [Built-In Tool System](../../mission.md)

## Contributing to Criteria

- [ ] Filesystem tooling supports the full lifecycle — read, write, in-place edit, delete, move, directory creation, pattern-based file discovery, and content search — with predictable behavior under the resolved (tool-level + agent-level) constraints *(F3 ships the full surface)*
- [ ] Each tool category enforces tool-level constraints — path scope, read-size caps, output caps, timeout caps, URL/host scope — that apply to all agents by default, and per-agent overrides can only narrow those constraint values, never widen them, with the narrowing invariant enforced at a single named resolution layer rather than ad-hoc in each tool *(F3 introduces the first real constraint values on F2's resolver seam — path scope + read-size cap; F4/F5 add execution + web)*
- [ ] Each kept tool has automated coverage proving it behaves correctly under happy-path use and under constraint-violation use (path-scope rejections, size-cap truncation, timeout caps, SSRF blocks, binary-file refusals) *(F3 covers filesystem subset)*
- [ ] Filesystem and execution tooling are architected for cross-platform support: platform-specific concerns (path semantics, shell selection, interpreter resolution, pty handling) are isolated behind a clear abstraction layer *(F3 keeps all platform-coupled code routing through `the_one/platform/`)*

---

## Pre-Flight

### Objective

Land the full filesystem surface (9 tools total: 3 existing + 6 new) and the first real constraint enforcement on F2's resolver seam. Add `edit_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `grep`. Introduce a per-category `FilesystemConfig` carrying four constraints — path-scope allowlist, denylist, read-size cap, binary-file allow-flag — and extend the resolver's marker vocabulary with two new sentinel markers (`NarrowPrefix` for path-list narrowing-by-prefix, `NarrowSuperset` for denylist narrowing-by-superset) alongside the existing `Narrow` / `Substitute`. The resolver remains the single audit point for narrowing semantics. Symlink-escape detection rides on F2's `canonicalize` + `is_within` (`Path.resolve` resolves symlinks; out-of-scope resolved paths refuse). All constraint-violation error messages use a custom `ConstraintError` exception type formatted as `[error] [constraint] {msg}` so small-model agents can recover gracefully. Includes a guided HAT leg validating that the agent reads constraint errors as actionable.

### Open Questions

- [x] **Path-scope narrow semantics** — Resolver gains `NarrowPrefix` and `NarrowSuperset` sentinel markers as siblings to `Narrow` / `Substitute`; per-marker dispatch in `_check_narrow`. Pivoted from initial `Substitute + model_validator` plan (architect-flagged: Pydantic v2 `mode="after"` instance-method validators do NOT receive `info`; introducing proper markers is cleaner architecturally and makes the resolver the single audit point per the mission criterion). (resolved: see Decision 1)
- [x] **Per-tool vs per-category Config** — `FilesystemConfig` shared across all 9 filesystem tools (resolved: see Decision 2)
- [x] **Default path allowlist** — `~` minus a curated denylist of system paths and credential locations (resolved: see Decision 3)
- [x] **Allowlist representation** — list of POSIX-canonicalized root path strings; prefix-containment narrowing (resolved: see Decision 4)
- [x] **Read-size cap default** — 1MB (NOT 50MB as the mission spec suggested; mission text overridden after context-budget analysis at flight-design time) (resolved: see Decision 5)
- [x] **HAT inclusion** — yes; F3 introduces user-visible constraint-violation behavior (resolved: see Decision 6)
- [x] **Pre-F3 maintenance fold-ins** — `tests/CONVENTIONS.md` + `_TOOL_CLASSES` doc note land in L1 alongside the resolver context-plumbing (resolved: see Decision 7)
- [x] **`edit_file` semantics** — old_string/new_string with uniqueness requirement; mirrors Anthropic's Edit tool (resolved: see Decision 8)
- [x] **`grep` semantics** — Python `re` regex by default, `-F` style fixed-string flag; 500-match cap with truncation marker (resolved: see Decision 9)
- [x] **TOCTOU residual after canonicalize** — accepted for F3; document as known limitation; F4 may harden if needed (resolved: see Decision 10)
- [x] **`read_size_cap_bytes` UI presentation** — dropdown with curated choices; UI hint embedded in Pydantic schema via `json_schema_extra={"ui_hint": "dropdown", "ui_choices": [...]}` so F6's admin form generator renders correctly without hand-coding (resolved: see Decision 11)

### Design Decisions

**Decision 1 — Resolver gains `NarrowPrefix` and `NarrowSuperset` markers**: `the_one/tools/resolver.py` adds two new sentinel marker classes alongside `Narrow` / `Substitute`:

- `NarrowPrefix` — for `list[str]` of paths. Agent-level value is narrow iff every agent path is a descendant of (or equal to) at least one tool path, checked via `the_one.platform.paths.is_within(agent_path, tool_path)`. Used by `FilesystemConfig.path_allowlist`.
- `NarrowSuperset` — for `list[T]` where the agent narrows by ADDING entries (more restrictive). Agent-level value is narrow iff every tool entry is also in the agent value (agent ⊇ tool, the inverse of `Narrow`'s `list` rule). Used by `FilesystemConfig.path_denylist`.

The `_check_narrow` helper extends with per-marker dispatch. `Narrow`'s existing list semantic (subset; agent ⊆ tool) is unchanged. Resolver remains the single audit point for narrowing semantics — the mission criterion "single named resolution layer rather than ad-hoc in each tool" is honored.

- Rationale (pivoted from initial `Substitute + model_validator` plan):
  - Pydantic v2's `model_validator(mode="after")` instance-method form does NOT receive `info: ValidationInfo`; only `mode="before"` (classmethod) and `field_validator(mode="after")` get `info`. The initial plan assumed an API that doesn't exist for our use case. Verified empirically before locking the design.
  - First-class markers document intent at the field declaration site, where readers look first. `path_allowlist: Annotated[list[str], NarrowPrefix]` is self-explanatory; `path_allowlist: Annotated[list[str], Substitute]` + a buried validator is not.
  - F5's URL/host allowlist will need similar prefix/glob semantics. Codifying once in the resolver prevents per-flight validator drift.
  - Sentinel-class identity dispatch (`m is NarrowPrefix`) is the same proven pattern as F2's `Narrow` / `Substitute`.
- Trade-off: the resolver grows two more markers. F3 verifies their semantic coherence with focused fixture tests; the marker count remains small (4 total).
- Forward-reference: F5's URL/host allowlist may add `NarrowGlob` or similar; contract stays additive.

**Decision 1.5 — Custom `ConstraintError` exception type**: F3 adds `ConstraintError(Exception)` in `the_one/tools/filesystem.py` (or a shared module). All policy-driven refusals raise this type with a human-readable message. Tool wrappers catch `ConstraintError` and format `[error] [constraint] {msg}`; other exceptions still format as `[error] {e}`. This avoids the brittle string-matching shape of "starts with `[constraint]`" and lets future debugging tools tell policy refusals from environmental failures.

**Decision 2 — Per-category `FilesystemConfig`**: All 9 filesystem tools share `FilesystemConfig` (`the_one/tools/filesystem.py`):

```python
from typing import Annotated
from pydantic import BaseModel, computed_field

from the_one.platform.paths import canonicalize
from the_one.tools.resolver import Narrow, NarrowPrefix, NarrowSuperset

class FilesystemConfig(BaseModel):
    path_allowlist: Annotated[list[str], NarrowPrefix] = ["~"]
    path_denylist: Annotated[list[str], NarrowSuperset] = list(DEFAULT_PATH_DENYLIST)
    read_size_cap_bytes: Annotated[int, Narrow] = 1_048_576  # 1MB; Decision 5
    allow_binary_files: Annotated[bool, Narrow] = False  # see "bool semantic" note

    # Pre-canonicalized PrivateAttrs — see Technical Approach code block for
    # the model_post_init eager-computation pattern that populates these.
    # NOTE: NOT `@computed_field @property` — those re-execute on every
    # access and would defeat caching. PrivateAttr stores the value once.
```

- Rationale: per-category beats per-tool because all 9 filesystem tools share the same security surface (same path scope, same binary-refusal semantic). Per-tool would duplicate the constraint constants. Decision 5 in F2 deferred this; F3 commits.
- Trade-off: a future filesystem tool that needs *different* path-scope semantics (e.g., a hypothetical `read_world_readable_file` with broader allowlist) would have to either extend `FilesystemConfig` or break category cohesion. Acceptable — no such tool is planned.
- The `path_allowlist` semantic is declared at the field via `NarrowPrefix` (Decision 1) — no model_validator needed.
- The `path_denylist` semantic is declared via `NarrowSuperset` — also resolver-enforced.
- **Pre-canonicalization caching**: uses `model_post_init` + `PrivateAttr` (NOT `@computed_field @property` — those re-execute on every access). The eagerly-computed `_canonical_allowlist` / `_canonical_denylist` are stashed on private attrs at construction time; subsequent reads are O(1). L2a tests assert `canonicalize` is called exactly `len(allowlist) + len(denylist)` times across 100 reads of the private attrs (proves caching).
- **Bool semantic**: `allow_binary_files: bool = False` (NOT `refuse_binary_files: bool = True`). The resolver's bool-narrowing rule from F2 is "False on tool means denied; agent True→False is narrowing, False→True is widening." With `allow_binary_files=False` as the tool default, an agent setting `True` correctly raises (agent widens permission). The original framing `refuse_binary_files=True` would have inverted the semantic and required custom narrowing — flagged in F2 debrief carryover #4 (renaming permission flags). Architectural lesson: name permission booleans positively (`allow_X=False`) so the resolver's natural "True=permissive" reading lines up.
- **Per-tool field consumption**: `mkdir` only reads `path_allowlist` + `path_denylist` (no read I/O). `delete_file` / `move_file` ditto. `read_file` / `edit_file` / `glob` / `grep` read all four. `write_file` reads path-scope only (writes are bounded by content the agent provides; output cap is F4/F5 territory). `list_dir` reads path-scope only. The shared Config is a strict superset of any single tool's needs.

**Decision 3 — Default path allowlist: `~` minus curated denylist**: Default `FilesystemConfig` ships with:

```python
path_allowlist = ["~"]
path_denylist = [
    # System secrets / credentials
    "~/.ssh", "~/.aws", "~/.gcloud", "~/.azure", "~/.config/gh",
    "~/.netrc", "~/.docker/config.json", "~/.kube",
    # Browser / app data
    "~/.mozilla", "~/.config/google-chrome", "~/.config/Code",
    "~/.config/Slack",
    # Agent's own internals
    "~/.the-one/secrets",
    # Outside ~ (system paths)
    "/etc", "/proc", "/sys", "/dev", "/boot", "/var/log",
]
```

- Rationale: user feedback was "I want to be able to do real work on the file system, recognizing we're running in a container now and this could be an install later." The `~`-as-allowlist matches both contexts: in the container, `~ = /root` and contains the agent's working state; as an install, `~` is the user's home and the agent can edit projects under it. Denylist protects credentials and system internals in both cases.
- The denylist is **paths**, not regex/glob, to keep the contract explainable to a non-technical operator (Decision 4 informs this).
- Tool-level denylist NEVER shrinks at the agent level (Decision 2's "narrow by superset" rule). An agent can add `~/projects/secret` to its own denylist; it cannot remove `~/.ssh` from the tool default.
- Forward-reference: when F6 ships the admin UI, the operator can edit both lists. Until then, defaults apply.
- Container-vs-install caveat documented in flight log: the denylist's `/root/` is NOT in the default list because in the container the agent IS root; on install the agent runs as the user and `/root` is system-only. Operator can add it via tool-level config when shipping as install.

**Decision 4 — Allowlist representation: list of POSIX-canonicalized root path strings**: The allowlist and denylist are `list[str]` of root paths. Path comparisons happen via `the_one.platform.paths.is_within(path, root)` (canonicalizes both sides → `Path.relative_to` check). Glob patterns and structured include/exclude rules are NOT supported in F3.
- Rationale: simplest representation operators can reason about. "List of folders that are allowed" is a 1-sentence explanation; "list of folders + glob patterns + exclusion rules" requires a manual. Mission constraint says "Small-model friendly: tool descriptions and constraint-violation error messages must be navigable by 7B-class models" — the same applies to operator config.
- Trade-off: cannot express "everything under ~/projects EXCEPT ~/projects/build". Operator would need to add specific subpaths to allowlist. Acceptable — the denylist provides the inverse (specific paths excluded).
- Forward-reference: if operator demand for glob-pattern allowlists emerges, a future flight can introduce a `NarrowGlob` marker and apply it where `NarrowPrefix` is today (or migrate the field type to `list[PathPolicy]` with a custom marker). Resolver remains the single audit point for narrowing.

**Decision 5 — Read-size cap: 1MB default (NOT 50MB), READ-side only**: The mission spec proposed 50MB; flight-design analysis revised this to 1,048,576 bytes (1MiB).
- Rationale: 50MB ≈ 10M tokens — exceeds every Claude context budget. The cap exists to protect agent context, not RAM/disk. 1MB ≈ 250K tokens, comfortable for Claude Opus 200K, ample headroom for 1M-context models, and forces healthy `offset/limit` pagination for the genuinely-large rare case. Most source-code files are well under 1MB (typical Python module: 5-50KB; even `package-lock.json` typically 100-500KB).
- **Scope: READ side only**. `read_size_cap_bytes` applies to the SIZE of files read into the agent context (`read_file`, `edit_file`'s read-then-write loop, `grep`'s per-file scan). It does NOT cap WRITE size — `write_file` and `edit_file` accept content of any size the agent provides. Output caps for tool RESPONSES (truncating tool output text) are F4/F5 territory.
- Override path: agents can narrow further (e.g., a research agent with a 100KB cap). Operators can raise the cap at tool level (up to whatever they want — the cap protects the agent's context, not the system).
- This cap is a `Narrow` field: agent override `<= tool default`. F2 resolver handles `int <=` natively.
- Mission Open Question "What's a reasonable size not to blow up context?" is now resolved at F3 design time. Mission text is not amended (mission docs are immutable post-active); the override is captured in this Decision and in the flight log.

**Decision 6 — HAT leg included**: F3 introduces user-visible behavior (the agent can hit constraint walls and must recover gracefully). The HAT leg validates the constraint-violation error strings are actionable for the agent.
- Rationale: F1 debrief promoted HAT to "design-completion gate" — surfaces design refinements through real LLM interaction. F3's constraint-violation strings are exactly the kind of voice/feel surface that benefits.
- The HAT leg is interactive (per agentic-workflow): the operator drives the agent through each constraint type (path-scope rejection, size-cap exceeded, binary-refusal, symlink-escape), confirms the agent recovers gracefully (e.g., notices the constraint, tries a different approach), and the Flight Director fixes any error-string-clarity issues inline.
- HAT lands AFTER the autonomous tool-implementation legs (so the constraint mechanism is exercised end-to-end against a real LLM) and BEFORE integration verification (so any HAT-driven fixes are caught by the final regression sweep).

**Decision 7 — Pre-F3 maintenance fold-ins**: L1 absorbs two F2-debrief carryovers:
- Create `tests/CONVENTIONS.md` documenting: `asyncio_mode = "auto"` test pattern, `monkeypatch.setenv("HOME", str(tmp_path))` for tilde tests, `httpx.MockTransport` `_install_mock` recursion-avoidance pattern, kill+reap timeout-budget assertions.
- Add a one-paragraph note to `the_one/agents.md` documenting `the_one.tools.builtins._TOOL_CLASSES` as the supported test monkeypatch seam.

These are tiny additive changes; folding into L1 (which also lands the new `NarrowPrefix` / `NarrowSuperset` resolver markers) avoids a separate maintenance leg.

Out of F3 scope (deferred to F4 / F6 / maintenance):
- `_kill_process_tree` extraction → F4 (execution-tool concern)
- Pre-F6 dev-DB default-provider seeding → F6 or maintenance
- Schema migration atomicity → maintenance (carried from F1 debrief, again from F2 debrief)
- `factory.py` duplicate comment "3" numbering → maintenance (cosmetic)

**Decision 8 — `edit_file` semantics**: `edit_file(path, old_string, new_string)`. `old_string` must appear EXACTLY ONCE in the file; if multiple matches, the agent must add surrounding context to make the match unique. Returns formatted line-numbered preview of the edit. Refuses binary files. Subject to read-size cap (file must be readable to be edited).
- Rationale: mirrors Anthropic's Edit tool — small-model agents already understand this contract. Uniqueness requirement prevents accidental multi-replacement.
- Trade-off: agents must read the file before editing to know the surrounding context. This is the intended workflow.
- Edge case: `old_string == new_string` is a no-op; refuse with a clear error so the agent doesn't silently spin.

**Decision 9 — `grep` semantics**: `grep(pattern, path, fixed_string=False, file_pattern="*")`. Default: Python `re` regex against UTF-8 file contents. `fixed_string=True` switches to `str.find`. `file_pattern` glob filters which files to search (default `*`). Cap: 500 matches with `... and N more` truncation marker. Skips binary files silently when `cfg.allow_binary_files` is False (the default; per Decision 2). Skips files exceeding `read_size_cap_bytes` silently (logs a count of skipped files in output).
- Rationale: regex by default matches grep-tool conventions; fixed-string flag for agents that want literal text. 500-match cap matches `list_dir`'s 500-entry pattern (existing convention).
- Trade-off: grep's cost scales with file count × file size. The 1MB read-size cap + binary skip naturally bound this; no additional time-based cap in F3.

**Decision 11 — `read_size_cap_bytes` UI presentation: dropdown with curated choices**: The cap is conceptually a finite set of sensible values, not a free-form integer. F6's admin UI must render this as a dropdown with the following choices (and their hint text), NOT a free-form numeric input. Operators are not expected to reason about arbitrary byte counts.

| Bytes | Label / hint |
|---|---|
| 51,200 | 50KB — very small models |
| 102,400 | 100KB — small/7B-class friendly |
| 262,144 | 256KB — most models comfortable |
| 524,288 | 512KB — middle |
| 1,048,576 | 1MB — default (Opus 200K headroom) |
| 5,242,880 | 5MB — Opus 1M only |

To make this readable by F6's admin form generator without F6 hand-coding the choices, F3 embeds the UI hint in the Pydantic schema via `Field(json_schema_extra=...)`:

```python
read_size_cap_bytes: Annotated[
    int,
    Narrow,
    Field(
        ge=1024,           # 1KB minimum sanity bound
        le=104_857_600,    # 100MB hard ceiling
        json_schema_extra={
            "ui_hint": "dropdown",
            "ui_choices": [
                {"value": 51_200, "label": "50KB — very small models"},
                {"value": 102_400, "label": "100KB — small/7B-class friendly"},
                {"value": 262_144, "label": "256KB — most models comfortable"},
                {"value": 524_288, "label": "512KB — middle"},
                {"value": 1_048_576, "label": "1MB — default (Opus 200K headroom)"},
                {"value": 5_242_880, "label": "5MB — Opus 1M only"},
            ],
        },
    ),
] = 1_048_576
```

- Rationale: Mission constraint says "small-model friendly" — that applies to the operator-facing UX too. A non-technical operator picking from `[50KB, 100KB, 256KB, 512KB, 1MB, 5MB]` with hint text understands the choice; faced with a free-form "bytes" field they'll either type something wrong or just leave the default.
- F6 reads `field.json_schema_extra.ui_hint == "dropdown"` to switch render strategy. Falls back to the field's natural type editor if no hint is present.
- Forward-reference: F3 establishes `ui_hint` / `ui_choices` as the conventional metadata keys. F4/F5 should reuse them for any other "finite-set-of-values" fields (e.g., `redirect_cap` in F5: `[3, 5, 10, 20, no-redirects]`). F6 builds the form-generator that reads them.
- The validation `ge=1024, le=104_857_600` happens at Pydantic-level regardless of UI; an agent or operator submitting a value outside the dropdown choices but inside the bounds is technically valid (the dropdown is a hint, not a hard constraint). If we want hard enforcement, F6 could add client-side validation; F3 keeps this open since the resolver enforces narrowing on the int value regardless.

**Decision 10 — TOCTOU residual after canonicalize, plus non-existent-target handling**: F3 accepts two narrow security windows:

1. **Classic TOCTOU**: between `_filesystem_check(path)` returning a canonical path and the tool actually opening the path, an attacker could swap a symlink. Stdlib doesn't provide atomic `openat()`-style operations.
2. **Non-existent path resolution**: `Path.resolve(strict=False)` (F2's `canonicalize` default) does NOT resolve symlinks for path components that DON'T EXIST. For `write_file("~/projects/safe/../../etc/secret")` where `secret` doesn't exist yet, lexical `..` processing makes this resolve to `/etc/secret` and the allowlist correctly rejects. But for symlinks pointing to non-existent targets, the resolution is platform-dependent.

**F3 mitigation**:
- For READ paths (`read_file`, `edit_file`, `glob`, `grep`): the file must exist to be read; `Path.resolve(strict=True)` semantics apply naturally because the I/O fails on non-existent paths regardless. `_filesystem_check` does NOT need an explicit existence check.
- For WRITE paths (`write_file`, `edit_file`'s write-back, `move_file`'s destination, `mkdir`): the **parent must exist and be in scope**, AND the parent must canonicalize cleanly (so any symlinks in the parent path are resolved). `_filesystem_check` checks the canonical of the path's parent, not the path itself, for write operations. The leaf component is then composed with the canonical parent.
- For `mkdir` specifically: deepest existing ancestor must be in scope; `parents=True` creates intermediate dirs as a side effect. Tests cover the `mkdir ~/scope/a/b/c` case where `a` doesn't exist.
- `move_file` checks BOTH source (must exist + be in scope) AND destination's parent (must exist + be in scope). Destination policy: explicit `overwrite: bool = False` parameter — refuse if destination exists and `overwrite=False`; permit overwrite when `overwrite=True`. Mirrors `mkdir`'s `exist_ok=True` precedent for "explicit override flag visible in tool schema."

- Rationale: F3's threat model is operator-trusted code preventing the agent from accidentally leaking secrets, NOT defending against a malicious filesystem actor. The TOCTOU window is microseconds and requires concurrent attacker access to the agent's filesystem.
- L2 includes explicit tests for: symlink to non-existent target, symlink to in-scope target, symlink to out-of-scope target, write to non-existent file in in-scope parent, write to file in non-existent parent (refuse).
- Documented as a known limitation in the flight log. F4 may harden via `os.O_NOFOLLOW` or similar if needed.

### Prerequisites

- [x] M05 Flight 2 landed and merged to `main` (commit `83a34bb`)
- [x] Schema is at v8 (verified: `the_one/db/schema.py:9 CURRENT_VERSION = 8`)
- [x] `the_one/tools/resolver.py` ships `Narrow` / `Substitute` / `_EmptyConfig` / `resolve()` / `_check_narrow` — F3 extends with `NarrowPrefix` / `NarrowSuperset` markers and per-marker dispatch arms in L1
- [x] `the_one/platform/paths.py` ships `canonicalize`, `safe_resolve`, `is_within` — F3 uses all three in `_filesystem_check`
- [x] All 9 target filesystem tools' positions identified: 3 existing (`read_file`, `write_file`, `list_dir`) + 6 new (`edit_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `grep`)
- [x] Tool ABC `Config: type[BaseModel] = _EmptyConfig` + `__init__(config)` ships in `the_one/tools/base.py` — F3's `FilesystemConfig` overrides the default
- [x] `BuiltinToolProvider._TOOL_CLASSES` module-level dict identified (`the_one/tools/builtins.py`) — F3 adds 6 new entries
- [x] `tests/test_aiat.py:30` fixture-scope fix landed in F2 L7 — AIAT live smoke is runnable
- [x] All flight-design Open Questions resolved (10/10)
- [ ] No port/network conflicts to verify — F3 doesn't introduce any new services, ports, or env vars
- [ ] User approves leg breakdown (Phase 4 sign-off)

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined → see Legs section below

---

## In-Flight

### Technical Approach

**Order rationale (8 legs, executed in dependency order):**

1. **Resolver narrow-marker extension + maintenance docs first** — add `NarrowPrefix` / `NarrowSuperset` sentinel markers; extend `_check_narrow` per-marker dispatch (mutual exclusion across all four markers); create `tests/CONVENTIONS.md`; document `_TOOL_CLASSES` test seam in `agents.md`. Foundational; everything downstream uses the new markers.
2. **`FilesystemConfig` + central `_filesystem_check` helper second** — defines all four constraint types as a single per-category Config; the central helper is what every filesystem tool calls before any I/O. No tool migration yet — pure scaffolding.
3. **Migrate 3 existing tools through `FilesystemConfig`** — `read_file` (size cap + binary refusal), `write_file` (path-scope only — content is from agent), `list_dir` (path-scope only). Establishes the integration pattern.
4. **Add `edit_file`** (gets its own leg because of complexity) — old/new uniqueness, line-numbered preview, integration with `_filesystem_check`.
5. **Add `delete_file`, `move_file`, `mkdir`** — three small file-level operations sharing the same `_filesystem_check` integration.
6. **Add `glob`, `grep`** — pattern-based discovery and content search; integrate `_filesystem_check` per-match for `grep`.
7. **HAT — guided constraint-violation walkthrough** (interactive; non-autonomous) — operator drives the agent through each constraint type; Flight Director iterates on error-string clarity.
8. **Integration verification** — full unit + browser + AIAT live smoke; F3-specific regression sweep.

**Key architectural shapes (locked at flight-design time):**

```python
# the_one/tools/resolver.py — NarrowPrefix and NarrowSuperset markers (L1)
class NarrowPrefix:
    """Marker: agent-level list[str] (paths) is narrowing iff every agent
    entry is a descendant of (or equal to) at least one tool entry. Used by
    FilesystemConfig.path_allowlist."""

class NarrowSuperset:
    """Marker: agent-level list[T] is narrowing iff every tool entry is also
    in the agent value (agent ⊇ tool — agent adds restrictions). Used by
    FilesystemConfig.path_denylist."""

# _check_narrow gains two additional dispatch arms keyed on marker class:
def _check_narrow_prefix(field_name, schema_name, tool_val, agent_val):
    from the_one.platform.paths import is_within
    if not (isinstance(tool_val, list) and isinstance(agent_val, list)):
        raise TypeError(f"NarrowPrefix on non-list field {schema_name}.{field_name}")
    for ap in agent_val:
        if not any(is_within(ap, tp) for tp in tool_val):
            raise ValueError(
                f"agent override widens {schema_name}.{field_name}; "
                f"'{ap}' not within any tool entry"
            )

def _check_narrow_superset(field_name, schema_name, tool_val, agent_val):
    if not (isinstance(tool_val, list) and isinstance(agent_val, list)):
        raise TypeError(f"NarrowSuperset on non-list field {schema_name}.{field_name}")
    for tp in tool_val:
        if tp not in agent_val:
            raise ValueError(
                f"agent override widens {schema_name}.{field_name}; "
                f"tool entry '{tp}' missing from agent value"
            )

# resolve()'s per-key dispatch grows two more checks:
#   has_narrow_prefix = any(m is NarrowPrefix for m in markers)
#   has_narrow_superset = any(m is NarrowSuperset for m in markers)
#
# Mutual exclusion across all four markers — at most one may be present per
# field. Resolver enforces explicitly:
#   marker_count = sum([has_narrow, has_narrow_prefix, has_narrow_superset, has_substitute])
#   if marker_count > 1:
#       raise TypeError(
#           f"field {schema.__name__}.{key} has multiple narrow/substitute "
#           "markers; declare exactly one"
#       )
#   if marker_count == 0:
#       raise ValueError(  # existing behavior
#           f"field {schema.__name__}.{key} has no Narrow/Substitute marker; "
#           "cannot resolve"
#       )
# Tests in tests/test_resolver.py::test_multi_marker_rejected lock this.
```

```python
# the_one/tools/filesystem.py — ConstraintError + FilesystemConfig (L2a)
from pathlib import Path
from typing import Annotated, Any
from pydantic import BaseModel, Field, PrivateAttr

from the_one.platform import canonicalize
from the_one.tools.resolver import Narrow, NarrowPrefix, NarrowSuperset


class ConstraintError(Exception):
    """Policy-driven refusal. Tool wrappers format as `[error] [constraint] {msg}`."""


# Curated denylist; rationale in Decision 3
DEFAULT_PATH_DENYLIST = [
    "~/.ssh", "~/.aws", "~/.gcloud", "~/.azure", "~/.config/gh",
    "~/.netrc", "~/.docker/config.json", "~/.kube",
    "~/.mozilla", "~/.config/google-chrome", "~/.config/Code",
    "~/.config/Slack",
    "~/.the-one/secrets",
    "/etc", "/proc", "/sys", "/dev", "/boot", "/var/log",
]


class FilesystemConfig(BaseModel):
    path_allowlist: Annotated[list[str], NarrowPrefix] = ["~"]
    path_denylist: Annotated[list[str], NarrowSuperset] = list(DEFAULT_PATH_DENYLIST)
    read_size_cap_bytes: Annotated[
        int,
        Narrow,
        Field(
            ge=1024,
            le=104_857_600,
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": [
                    {"value": 51_200, "label": "50KB — very small models"},
                    {"value": 102_400, "label": "100KB — small/7B-class friendly"},
                    {"value": 262_144, "label": "256KB — most models comfortable"},
                    {"value": 524_288, "label": "512KB — middle"},
                    {"value": 1_048_576, "label": "1MB — default (Opus 200K headroom)"},
                    {"value": 5_242_880, "label": "5MB — Opus 1M only"},
                ],
            },
        ),
    ] = 1_048_576  # See Decision 11
    allow_binary_files: Annotated[bool, Narrow] = False  # Decision 2 bool semantic note

    # Eagerly-computed canonical paths cached as PrivateAttr.
    # NOT @computed_field @property — those re-execute on every access and
    # would defeat the N×M resolve avoidance. PrivateAttr stores the value
    # once at construction; subsequent reads are O(1).
    _canonical_allowlist: list[Path] = PrivateAttr(default_factory=list)
    _canonical_denylist: list[Path] = PrivateAttr(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        # Runs after Pydantic finishes constructing the model. Compute the
        # canonical paths once and stash them on the private attrs.
        self._canonical_allowlist = [canonicalize(p) for p in self.path_allowlist]
        self._canonical_denylist = [canonicalize(p) for p in self.path_denylist]
```

```python
# the_one/tools/filesystem.py — _filesystem_check helpers (L2b)
def _filesystem_check(path: str | Path, cfg: FilesystemConfig) -> Path:
    """Canonicalize path; verify within allowlist and not within denylist.
    Raises ConstraintError on violation. Resolves symlinks (canonicalize uses
    Path.resolve), so symlink-escape is detected as 'outside allowlist'."""
    canonical = canonicalize(path)
    if not any(canonical == r or _is_descendant(canonical, r) for r in cfg._canonical_allowlist):
        raise ConstraintError(f"path '{canonical}' outside allowlist")
    for deny in cfg._canonical_denylist:
        if canonical == deny or _is_descendant(canonical, deny):
            raise ConstraintError(f"path '{canonical}' inside denylist '{deny}'")
    return canonical


def _filesystem_check_write_parent(path: str | Path, cfg: FilesystemConfig) -> Path:
    """For write operations on files that don't yet exist: check that the
    PARENT is canonicalizable (exists; symlinks resolved) and in scope. Then
    compose the leaf with the canonical parent.
    Raises ConstraintError on violation, FileNotFoundError if parent missing."""
    p = Path(path).expanduser()
    canonical_parent = canonicalize(p.parent)
    if not canonical_parent.exists():
        raise FileNotFoundError(f"parent does not exist: {canonical_parent}")
    composed = canonical_parent / p.name
    return _filesystem_check(composed, cfg)


def _is_descendant(path: Path, root: Path) -> bool:
    """True if path is strictly under root (not equal). Both pre-canonicalized."""
    try:
        path.relative_to(root)
        return path != root
    except ValueError:
        return False


def _check_read_size(path: Path, cfg: FilesystemConfig) -> int:
    """Return file size if under cap; else raise ConstraintError."""
    size = path.stat().st_size
    if size > cfg.read_size_cap_bytes:
        raise ConstraintError(
            f"file size {size} bytes exceeds cap "
            f"{cfg.read_size_cap_bytes} bytes; use offset/limit to paginate"
        )
    return size


def _is_binary(path: Path) -> bool:
    """Sniff first 8KB for null bytes (canonical binary heuristic)."""
    with path.open("rb") as f:
        chunk = f.read(8192)
    return b"\x00" in chunk
```

**Tool-level error formatting** (per tool's `execute()`):

```python
async def execute(self, path: str, ...) -> str:
    cfg: FilesystemConfig = self._config
    try:
        canonical = _filesystem_check(path, cfg)
        # ... do work ...
        return result
    except ConstraintError as e:
        return f"[error] [constraint] {e}"
    except Exception as e:
        return f"[error] {e}"
```

The two-clause `try/except ConstraintError / except Exception` lets the agent distinguish "tool failed for environmental reasons" (`[error] {e}`) from "tool refused for policy reasons" (`[error] [constraint] {msg}`). Forward-reference: F4/F5 use the same `ConstraintError` type for output caps, timeout caps, SSRF blocks.

### Checkpoints

- [ ] **Resolver markers extended** — `NarrowPrefix` and `NarrowSuperset` sentinel classes exported from `the_one/tools/resolver.py`; `_check_narrow` dispatch covers all four markers (mutually exclusive); existing F2 resolver tests pass unchanged; new fixture tests cover both marker types' happy + violation paths
- [ ] **`FilesystemConfig` landed** — Pydantic Config with four annotated fields + resolver-marker dispatch (`NarrowPrefix` / `NarrowSuperset` / `Narrow`); pre-canonicalization via `model_post_init` + `PrivateAttr`; central `_filesystem_check` helper exists; unit tests cover happy path + every constraint type (path-scope rejection, denylist hit, size cap, binary refusal, symlink escape) AND the caching invariant (canonicalize called exactly len(allowlist)+len(denylist) times across N reads)
- [ ] **3 existing filesystem tools migrated** — `read_file`/`write_file`/`list_dir` route paths through `_filesystem_check`; `read_file` enforces size cap and binary refusal; tests prove behavior under both allow and deny
- [ ] **`edit_file` shipped** — uniqueness-checked old/new replacement; refuses binary; subject to size cap; tests cover happy + multi-match-error + binary-refusal + size-exceeded
- [ ] **`delete_file`, `move_file`, `mkdir` shipped** — each uses `_filesystem_check`; `mkdir` `parents=True, exist_ok=True` semantic; `move_file` checks both source and destination paths; tests cover each
- [ ] **`glob`, `grep` shipped** — pattern discovery + content search; `grep` skips binary and oversized files silently with skip count in output; 500-match cap with truncation marker
- [ ] **HAT pass complete** — operator-driven walkthrough of all four constraint types; agent recovers gracefully on every constraint hit; any error-string-clarity issues fixed inline
- [ ] **Integration verified** — full unit suite green (modulo pre-existing CSS-token red); browser suite green; AIAT live smoke green; F3 regression sweep (no leftover platform-coupled calls; no tools missing `Config = FilesystemConfig`; no inline `Path.expanduser().resolve()` calls outside `the_one/platform/`) returns zero unexpected matches

### Adaptation Criteria

**Divert if**:
- The `NarrowPrefix` / `NarrowSuperset` markers prove insufficient for a real F3 case (e.g., the user wants prefix-narrowing but with denylist subtraction). Fall back to introducing a `model_validator(mode="before")` per-tool callback that receives the merged dict before construction — this is the next-most-natural Pydantic v2 escape hatch, and it sidesteps the `mode="after"`-doesn't-receive-info issue. Document and proceed.
- HAT (L7) surfaces a constraint-violation error string that small-model agents systematically fail to recover from. Iterate on the error string AND the tool description in-flight; if the issue is fundamental to the constraint design (not the messaging), escalate to a Decision-revision.
- L4 (`edit_file`) hits an unanticipated multi-replacement edge case (e.g., `old_string` matches across file encodings). Document and either narrow the contract or extend tests; no full divert needed.
- The default denylist (Decision 3) clashes with a real workflow during HAT (e.g., the agent legitimately needs to read a `~/.config/Code/...` file as part of dev work). Operator can override at tool level immediately; flight-design assumption documented as not-load-bearing.
- Symlink-escape detection produces false positives on legitimate symlinked workflows (e.g., a project under `~/projects` that symlinks to `~/work`). Document; F3 keeps strict resolve-and-check (Decision 10's threat model assumes operator-trusted setup).

**Acceptable variations**:
- Whether `FilesystemConfig` lives in `the_one/tools/filesystem.py` (next to its consumers, matching F2's `MCPSourceConfig`-next-to-MCP pattern) or `the_one/tools/configs/filesystem.py` (anticipating F4/F5 sibling Configs). Default to in-file unless L2 implementation finds the file getting unwieldy.
- Whether `_filesystem_check` is a module-level function or a method on `FilesystemConfig`. Default to module-level (testable in isolation; matches F2 `the_one/platform/paths.py` style).
- Whether `glob` matches Python's `pathlib.Path.glob` semantics or shell-style `**`. Default to pathlib (predictable; matches `list_dir`'s use of `rglob`).
- Whether `grep` outputs `path:line_num:match` (grep-style) or formatted blocks. Default to grep-style; small-model-friendly.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [ ] `01-resolver-narrow-markers-and-maintenance-docs` — Add `NarrowPrefix` and `NarrowSuperset` sentinel marker classes to `the_one/tools/resolver.py`. Extend `_check_narrow` (or split into per-marker helpers) with prefix-containment and superset-membership dispatch arms. Update `resolve()`'s per-key dispatch loop with **explicit mutual-exclusion enforcement**: count markers per field; raise `TypeError` if more than one of `{Narrow, NarrowPrefix, NarrowSuperset, Substitute}` is present. Tests in `tests/test_resolver.py::TestNarrowPrefix` and `::TestNarrowSuperset` cover happy + violation + non-list-type-error; `::test_multi_marker_rejected` locks the mutual-exclusion contract. Create `tests/CONVENTIONS.md` documenting the four F2 patterns (asyncio_mode, monkeypatch.setenv HOME, httpx MockTransport, kill+reap budgets) — each with a runnable code snippet. Add a paragraph to `the_one/agents.md` pinning `_TOOL_CLASSES` as the supported test seam AND documenting the `ui_hint`/`ui_choices` Pydantic-schema convention introduced in Decision 11 (so F4-F6 reuse the same metadata keys for finite-set fields). Foundational scaffolding leg; ~100-130 LoC change + docs.

- [ ] `02a-filesystem-config-pydantic-model` — Define `FilesystemConfig` Pydantic model in `the_one/tools/filesystem.py` with the four annotated fields (`path_allowlist: NarrowPrefix`, `path_denylist: NarrowSuperset`, `read_size_cap_bytes: Narrow + json_schema_extra ui_hint`, `allow_binary_files: Narrow`). Define `DEFAULT_PATH_DENYLIST` constant. Define `ConstraintError(Exception)`. Add `model_post_init` that eagerly computes and stores `_canonical_allowlist` / `_canonical_denylist` on `PrivateAttr` instances (NOT `@computed_field @property` — those re-execute on every access and would defeat caching). Tests in `tests/test_filesystem_config.py` cover: default instantiation; resolver-level narrowing through F2's `resolve()` for each marker (happy + violation per field); **caching invariant** (mock `canonicalize`, instantiate Config with N allowlist + M denylist entries, read each PrivateAttr 100 times, assert call_count == N + M); `Field.json_schema_extra` ui_hint surfaces correctly via `model_json_schema()`.

- [ ] `02b-filesystem-check-helpers` — Implement `_filesystem_check`, `_filesystem_check_write_parent`, `_is_descendant`, `_check_read_size`, `_is_binary` module-level helpers in `the_one/tools/filesystem.py`. Tests in `tests/test_filesystem_helpers.py` cover the full matrix:
  - `_filesystem_check`: happy, path outside allowlist, path inside denylist, symlink to in-scope target, symlink to out-of-scope target (allowlist rejects), symlink to non-existent target.
  - `_filesystem_check_write_parent`: happy (parent exists, in scope), parent missing (FileNotFoundError), parent out of scope (ConstraintError), parent contains `..` (canonicalized correctly).
  - `_check_read_size`: under cap, equal to cap, over cap.
  - `_is_binary`: text file (False), binary file with null in first 8KB (True), text file with null at offset >8KB (False — heuristic accepts this corner).
  No tool changes yet — pure helper testing.

- [ ] `03-migrate-existing-filesystem-tools` — `ReadFileTool`, `WriteFileTool`, `ListDirTool` all set `Config = FilesystemConfig`. `ReadFileTool.execute` calls `_filesystem_check` → `_check_read_size` → `_is_binary` (refuses if NOT `cfg.allow_binary_files`). `WriteFileTool.execute` calls `_filesystem_check_write_parent` (parent must exist + be in scope) and bypasses size/binary checks (write content is agent-provided, no read I/O). `ListDirTool.execute` calls `_filesystem_check` for the listed root. Existing tests in `tests/test_filesystem_tools.py` extended to cover the constraint-violation cases. Standardized `[error] [constraint] ...` error format via `ConstraintError`.

- [ ] `04-add-edit-file-tool` — `EditFileTool` (`name="edit_file"`): old_string/new_string with uniqueness. Reads file via `_filesystem_check` + `_check_read_size` + `_is_binary`. Validates `old_string != new_string` (refuse no-op). Validates `text.count(old_string) == 1` (refuse if zero or multiple matches; clear error encouraging the agent to add context). Writes back via `_filesystem_check_write_parent` semantics (parent must remain in scope after the round-trip). Returns formatted line-numbered preview of the edit (lines surrounding the change, with `+`/`-` markers). Tests in `tests/test_filesystem_tools.py::TestEditFileTool` cover happy, multi-match-error, no-match-error, identical-strings-error, binary-refused, size-exceeded, write-parent-out-of-scope. Add to `BuiltinToolProvider._TOOL_CLASSES`. Add to Studio's `TOOL_CATEGORIES` (filesystem category).

- [ ] `05-add-delete-move-mkdir-tools` — Three small file-level operations:
  - `DeleteFileTool` (`name="delete_file"`, args `path`): `_filesystem_check`; `Path.unlink()`; refuse on directories (use a separate `delete_dir` if needed in future). Tests: happy, path-scope-reject, denylist-reject, file-doesn't-exist (FileNotFoundError → `[error] {e}`), is-a-directory (refuse with clear error).
  - `MoveFileTool` (`name="move_file"`, args `source`, `destination`, `overwrite: bool = False`): `_filesystem_check(source)` (source must exist + be in scope); `_filesystem_check_write_parent(destination)` (destination's parent must exist + be in scope). If destination already exists: refuse with `ConstraintError` when `overwrite=False` (default); permit and overwrite when `overwrite=True`. Mirrors `mkdir`'s `parents=True, exist_ok=True` precedent for "explicit override flag". The `overwrite` parameter is in the tool's JSON schema so small-model agents can discover it. Tests cover happy, source-out-of-scope, destination-parent-out-of-scope, destination-exists-refuse-default, destination-exists-overwrite-permit, source-doesn't-exist.
  - `MkdirTool` (`name="mkdir"`, args `path`): `_filesystem_check_write_parent(path)` semantics — deepest existing ancestor must be in scope; `Path.mkdir(parents=True, exist_ok=True)`. Tests cover happy (existing parent), happy (deep nested where intermediate dirs are created), parent-out-of-scope-reject, path-itself-out-of-scope-reject.
  Add three entries to `_TOOL_CLASSES` and `TOOL_CATEGORIES`.

- [ ] `06-add-glob-grep-tools` — Two pattern-matching tools:
  - `GlobTool` (`name="glob"`, args `pattern`, `root="."`): wraps `Path.rglob`/`glob`; **`_filesystem_check` per match** (not just per-root; matched files could resolve to symlinks that escape scope). Returns sorted list of matches as `path` per line; cap at 500 with `... and N more` truncation. Tests cover happy, no-match, glob-pattern-syntax (`**/*.py`), match-outside-scope-skipped (with skip count in output), 500-match cap.
  - `GrepTool` (`name="grep"`, args `pattern`, `path`, `fixed_string=False`, `file_pattern="*"`): walks files under `path` matching `file_pattern`; per-file `_filesystem_check`; per-file `_check_read_size` (skip oversized silently with count in output); per-file `_is_binary` (skip silently with count in output); regex (default) or fixed-string (`-F` semantic) match per line; reports first 500 matches as `path:line_num:matched_line` with `... and N more` truncation; per-file match cap to prevent a single huge-match-count file from monopolizing output (cap: 100 matches per file before moving on). Tests cover happy, no-match, regex-syntax-error, fixed-string mode, binary-skip count, size-skip count, 500-match global cap, 100-match per-file cap, file_pattern filter, recursive descent.
  Add two entries to `_TOOL_CLASSES` and `TOOL_CATEGORIES`.

- [ ] `hat-constraint-violation-walkthrough` *(interactive; non-autonomous)* — Operator drives the agent through each constraint type and verifies graceful recovery:
  1. **Path-scope rejection**: agent tries to read `/etc/passwd` → expects `[error] [constraint] path '...' outside allowlist`; agent should recognize "not allowed" and try a different file under `~`.
  2. **Denylist hit**: agent tries to read `~/.ssh/id_rsa` → expects `[error] [constraint] path '...' inside denylist '~/.ssh'`; agent should NOT loop trying variations.
  3. **Size cap**: agent tries to read a 2MB file (operator creates one in scope) → expects `[error] [constraint] file size 2097152 bytes exceeds cap 1048576 bytes; use offset/limit to paginate`; agent should use `offset/limit`.
  4. **Binary refusal**: agent tries to read `/usr/bin/ls` (in scope on container? if yes; else operator creates a binary fixture) → expects `[error] [constraint] binary file refused (set allow_binary_files=true to permit)`; agent should not retry.
  5. **Symlink-escape**: operator creates a symlink under `~/projects/work` pointing to `/etc/passwd`; agent tries to read via the symlink → expects allowlist-rejection (because canonical resolution lands at `/etc/passwd`).
  6. **Edit-file uniqueness**: agent edits a file with `old_string` that matches multiple times → expects clear error encouraging context addition; agent recovers by adding surrounding context.
  7. **`move_file` overwrite refused**: agent tries to move A to existing B without `overwrite=True` → expects refusal with hint about the flag; agent retries with `overwrite=True`.

  **Note for binary scenario (#4)**: The container has `/usr/bin/ls` etc. but those are OUTSIDE the default `~` allowlist, so allowlist-rejection fires before binary-check. To exercise binary refusal cleanly, the operator **pre-creates a binary fixture under `~`** (e.g., `cp /usr/bin/ls ~/binary-fixture`) before the HAT session.
  Flight Director walks operator through each step, records agent's response, fixes error strings inline (spawning developer-agent fixes per step) if the agent's recovery is poor. No autonomous code changes between HAT steps.

- [ ] `08-integration-verification` — Full default unit suite (target: 600+ passing, +80-100 net new from F2 tip; modulo pre-existing CSS-token red); browser suite green; AIAT live smoke green (F2 L7 fixed the fixture; F3 may add AIAT cases for new tools but minimum viable is the existing suite still passing). F3 regression sweeps:
  ```
  rg -n 'Path\([^)]+\)\.expanduser\(\)\.resolve\(\)' the_one/tools/   # empty
  rg -n 'Config\s*=\s*_EmptyConfig' the_one/tools/filesystem.py        # empty
  rg -n '^class \w+Tool' the_one/tools/filesystem.py | wc -l            # 9
  rg -n 'is_within\(' the_one/tools/filesystem.py                       # only inside _filesystem_check helpers, NOT inlined per-tool
  rg -n 'NarrowPrefix\|NarrowSuperset' the_one/tools/                   # only resolver.py + filesystem.py imports
  rg -n 'class ConstraintError' the_one/                                # exactly 1
  ```
  Documentation: update `agents.md` filesystem-tool section to reflect 9 tools + the four constraint types + the two new resolver markers; update `CLAUDE.md` Tool Configuration Layer section to document `NarrowPrefix` / `NarrowSuperset` semantics. Update mission Open Questions to mark all F3-assigned items resolved. Append L8 final entry to flight log.

---

## Post-Flight

### Completion Checklist

- [x] All legs landed (L1-L8; L7 is the optional HAT)
- [x] `the_one/tools/resolver.py` exports `NarrowPrefix` and `NarrowSuperset` markers; `_check_narrow` dispatches all four markers correctly; existing F2 tests pass unchanged
- [x] `FilesystemConfig` shipped with 4 annotated fields + resolver-marker dispatch + `model_post_init`/`PrivateAttr` caching; `_filesystem_check`, `_filesystem_check_write_parent`, `_is_descendant`, `_check_read_size`, `_is_binary` helpers in place
- [x] All 9 filesystem tools (`read_file`, `write_file`, `list_dir`, `edit_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `grep`) `Config = FilesystemConfig`; route paths through `_filesystem_check`
- [x] Standardized `[constraint] ` prefix used for every policy-driven refusal
- [x] HAT pass complete; constraint-violation error strings validated against a real LLM
- [x] Default unit suite green (modulo pre-existing CSS-token red)
- [x] Browser suite green
- [ ] AIAT live smoke green (existing tests still pass; new F3 AIAT cases optional) — environmental: container has no provider configured (`Agent 'default' has no provider configured`); 4 fail / 2 pass. Pre-existing condition unrelated to F3 code; documented and accepted per L8 leg spec.
- [x] No regressions in F1-F2 surfaces (the_one/db/schema.py REMOVED set unchanged; resolver markers unchanged; platform package unchanged structurally)
- [x] `tests/CONVENTIONS.md` exists; `_TOOL_CLASSES` documented in `agents.md`
- [ ] Code committed; flight log updated; flight status set to `landed` — flight-log + status updated in L8; commit deferred to Flight Director per agentic-workflow.

### Verification

**Static (grep / read):**

```bash
# FilesystemConfig is the Config for all 9 filesystem tools
rg -n 'Config = FilesystemConfig' the_one/tools/filesystem.py
# Expected: 9 matches (one per tool class)

# _filesystem_check is invoked from every filesystem tool's execute()
rg -n '_filesystem_check\(' the_one/tools/filesystem.py
# Expected: 9+ matches (one per tool, plus helpers)

# All 6 new tools registered in BuiltinToolProvider
rg -n '"(edit_file|delete_file|move_file|mkdir|glob|grep)"' the_one/tools/builtins.py
# Expected: 6 matches

# Resolver context-plumbing landed
rg -n 'class NarrowPrefix\|class NarrowSuperset' the_one/tools/resolver.py
# Expected: 2 matches

# tests/CONVENTIONS.md exists
test -f tests/CONVENTIONS.md && echo OK

# No leftover inline platform-coupled calls
rg -n 'Path\([^)]+\)\.expanduser\(\)\.resolve\(\)' the_one/tools/
# Expected: empty
```

**Dynamic (test suite):**

```bash
make rebuild               # full rebuild against new code
make test-unit             # default unit suite must pass
make test-browser          # browser suite must pass
docker exec the-one pytest -m live tests/test_aiat.py  # live smoke must pass

# Resolver NarrowPrefix smoke
docker exec the-one python -c "
from typing import Annotated
from pydantic import BaseModel
from the_one.tools.resolver import resolve, NarrowPrefix

class Cfg(BaseModel):
    paths: Annotated[list[str], NarrowPrefix] = []

# Tool allows /home/u; agent narrows to /home/u/projects (prefix-descendant)
r = resolve(Cfg, {'paths': ['/home/u']}, {'paths': ['/home/u/projects']})
assert r.paths == ['/home/u/projects'], r
# Agent attempts to widen to /etc — must raise
try:
    resolve(Cfg, {'paths': ['/home/u']}, {'paths': ['/etc']})
    assert False, 'should have raised'
except ValueError as e:
    assert 'widens' in str(e), str(e)
print('OK')
"

# FilesystemConfig narrowing smoke
docker exec the-one python -c "
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools.resolver import resolve
# Tool allows ~/projects; agent narrows to ~/projects/foo (within tool scope)
r = resolve(FilesystemConfig, {'path_allowlist': ['~/projects']}, {'path_allowlist': ['~/projects/foo']})
assert r.path_allowlist == ['~/projects/foo']
# Agent attempts to widen — must raise
try:
    resolve(FilesystemConfig, {'path_allowlist': ['~/projects']}, {'path_allowlist': ['/etc']})
    assert False, 'should have raised'
except Exception as e:
    assert 'widens' in str(e).lower() or 'not within' in str(e).lower(), str(e)
print('OK')
"
```

**Manual (HAT):** L7 walkthrough — operator drives the agent through 5 constraint scenarios and confirms graceful recovery on each.

---

## Architect Q&A — design refinements captured

(To be filled by Phase 5b architect review.)
