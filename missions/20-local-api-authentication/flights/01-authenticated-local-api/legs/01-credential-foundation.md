# Leg: credential-foundation

**Status**: landed
**Flight**: [Authenticated Local API End-to-End](../flight.md)

## Objective

Deliver the credential primitive the whole flight rests on — its shape, its
exclusive-mode creation, its constant-time verification, the identified-caller
type a successful lookup yields, the lookup seam a second credential source can
register against, and a command-line rotate — with nothing yet enforced on any
request path.

## Context

Design decisions from the flight this leg implements:

- **DD1 — Credential shape**: an opaque string carrying a *public identifier*
  and a *secret*, distinguishable by prefix. The identifier exists so a future
  store can revoke by identifier and so logs and errors can name a credential
  without printing its secret.
- **DD2 — Storage and creation**: a file in the resolved data directory,
  created via an exclusive open at mode `0600` in a single syscall.
- **DD8 — Authorization resolves a caller identity behind a lookup seam**: the
  gate yields an identified caller, not a boolean, and credential lookup goes
  through a seam a second source can register against.
- **DD9 — Rotation is command-line only**: a new subcommand on the existing
  `sys.argv` dispatch. No endpoint, no UI control.
- **DD12 — the long-lived credential and the one-time handoff credential are
  two different credentials with two different lifetimes.** This leg builds
  **only the long-lived, persisted one**. The one-time handoff credential is
  per-process, in-memory, and belongs to `gate-middleware`. The flight spec
  names conflating them as the likeliest implementation error in this flight —
  do not build handoff machinery here.

Where this sits: this leg produces a library and a CLI command and touches no
request path. `make test-unit` must be green at leg end, exactly as it is now.
The first leg permitted to go red is `enforce-and-migrate-harness`, two legs
away.

**Prior-leg learnings**: none — this is the first leg of the flight.

### Two codebase facts that will otherwise mislead the implementer

1. **`the_one/encryption.py` is the wrong precedent for file creation.**
   `Encryptor.rotate_key` and `get_encryptor` both use `write_bytes()` followed
   by `os.chmod(..., 0o600)`. GitHub issue #165 explicitly asked for "the same
   handling as `encryption.key`" — flight reconnaissance rejected that
   instruction. The correct precedent is in
   `the_one/interfaces/web/api.py`, in the connector-key rotation path, whose
   own comment records why: *"Mode 0o600 is set at creation time via os.open
   (Path.write_bytes followed by chmod has a brief world-readable window)."*
   Follow that one. Do **not** "fix" `encryption.py` in this leg — it is
   pre-existing, out of scope, and belongs to its own change.

2. **`tests/test_auth_posture_probe.py` is not about this API.** The name
   invites the assumption that it pins the current unauthenticated posture and
   must be inverted. It does not. It covers
   `the_one.mcp.transports.streamable_http._probe_auth_posture`, which
   classifies the auth posture of *outbound* MCP servers the-one connects to.
   It is unaffected by this flight and must not be modified.

## Inputs

What exists before this leg runs:

- `the_one/config.py:Settings` — `data_dir` (a `Path`, `platformdirs`-resolved,
  overridable via `THE_ONE_DATA_DIR` through the `THE_ONE_` env prefix) and
  `Settings.ensure_dirs()`, which creates the directory and must never raise.
- `the_one/interfaces/web/api.py` — the connector-key rotation block: the
  canonical `os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL,
  0o600)` → `os.write` → `os.fsync` → `os.replace` sequence.
- `the_one/main.py:cli_entry` — a plain `sys.argv[1:]` if/elif dispatch over
  `chat | serve | app | version | doctor`, ending in a usage block and
  `sys.exit(1)`.
- `the_one/encryption.py` — the module-level `_encryptor_cache` keyed by
  resolved `data_dir`, as an example of the project's caching idiom (and, per
  the Context note, as an anti-precedent for file mode handling).
- `tests/CONVENTIONS.md` — `asyncio_mode = "auto"` (no `@pytest.mark.asyncio`),
  and `monkeypatch.setenv("HOME", str(tmp_path))` for tests touching `~`.

## Outputs

What exists after this leg completes:

- A new credential module at the `the_one/` package root, sibling to
  `encryption.py`. **Not** under `the_one/interfaces/web/` — it is consumed by
  the CLI (`main.py`, this leg), the desktop shell
  (`the_one/interfaces/desktop/shell.py`, `operational-callers`), and the web
  middleware (`gate-middleware`); rooting it in the web interface package would
  make the launcher import the web layer for a non-web concern. `encryption.py`
  sets exactly this precedent for a security primitive with cross-layer
  consumers.
- A credential file in the resolved data directory, auto-created on first use
  at mode `0600`.
- A new subcommand on `cli_entry` that rotates the credential.
- A new unit test module under `tests/`.
- `packaging/windows/README.md` — the one line that enumerates the CLI
  subcommands, updated to include the new one.

## Acceptance Criteria

- [x] A credential value parses into a public identifier and a secret, and
      carries a type-distinguishing prefix. Its `repr()` and `str()` reveal the
      identifier but never the secret — asserted directly, not by inspection.
- [x] A successful lookup yields an **identified caller** object carrying at
      minimum the credential's identifier and which source resolved it. A
      failed lookup yields `None`. Nothing in the module returns a bare
      `True`/`False` for "is this caller authorized."
- [x] Verification of a presented secret uses a constant-time comparison. A
      test asserts the comparison primitive is used, so that a later refactor
      to `==` fails rather than silently regressing.
- [x] On first use in a data directory with no credential file, the file is
      created and the resulting credential round-trips: a second read returns
      the same value.
- [x] The credential file's mode is exactly `0600` — owner read/write, no group
      or other bits of any kind. Asserted on a real file in `tmp_path`, not
      mocked, and **guarded with `@pytest.mark.skipif(os.name != "posix", ...)`**
      following the identical assertion at
      `tests/test_encryption.py:TestGetEncryptor.test_key_file_permissions`.
      Windows synthesizes `st_mode` from a single read-only bit and does not
      model owner/group/other, so an unguarded assertion can never pass there.
- [x] **There is no window during creation in which the file is
      group- or world-readable.** Verified structurally: the test asserts the
      creation path opens with `O_EXCL` and a `0o600` mode argument in a single
      call and never calls `os.chmod` on the credential path. (A timing-based
      race test would be flaky; the structural assertion is what actually pins
      the property.)
- [x] Creation is atomic with respect to readers — a partially-written file is
      never observable at the canonical path.
- [x] A second credential source can be registered against the lookup seam, and
      a credential it owns resolves to an identified caller naming that source
      — **with no change to the resolution entry point**. The test registers an
      in-memory source alongside the file-backed one and asserts both resolve
      through the same call. This is the flight's mission-criterion-7 evidence;
      it is a real test, not a comment claiming extensibility.
- [x] The lookup reflects an on-disk rotation performed by another process
      **without a restart of the reading process**. See Cache Contract below.
- [x] The rotate subcommand replaces the credential, exits `0`, and prints
      confirmation that the credential was replaced — **without printing the
      secret**. The replacement differs from the prior value and the file mode
      is still exactly `0600` afterward.
- [x] The rotate subcommand operates on the data directory the settings
      resolve, so `THE_ONE_DATA_DIR` targets a scratch directory. A test proves
      this by rotating against a `tmp_path` data dir and asserting the
      operator's default directory was untouched.
- [x] Rotation is atomic: an interrupted rotate leaves the previous credential
      intact and readable, never a truncated or absent file.
- [x] The usage text emitted by the unrecognized-argument branch of `cli_entry`
      lists the new subcommand, and **both** CLI-subcommand enumerations in
      `packaging/windows/README.md` match it — the directory-listing comment
      (`chat|serve|app|version|doctor`) and the later installer prose
      (`chat|serve|doctor|version`). The prose list's omission of `app` is
      deliberate — `app` is described in the same sentence — so preserve that
      omission and add only the new subcommand.
- [x] The new test module is registered in the curated Windows lane — added to
      the explicit file list in `ci/tasks/windows-tests.yml` **and** its
      documented mirror, the `windows` job in `.github/workflows/test.yml`. Both
      carry a MAINTENANCE comment requiring this for any test exercising
      platform-divergent behavior; `tests/test_encryption.py` is already listed
      for exactly this reason. This leg's highest-risk property —
      `st_mtime_ns` behavior across an `os.replace` — is precisely what that
      lane exists to catch, and it will otherwise go unverified on real Windows.
- [x] `make test-unit` is green. This leg enforces nothing and must not redden
      a single existing test.

## Cache Contract

Called out explicitly because the flight's acceptance depends on it and it is
easy to miss: the behavior test
(`tests/behavior/local-api-auth-session-lifecycle.md`) rotates the credential in
step 12 and, in step 13, expects the **already-running** server to stop
honouring the pre-rotation session — **with no server restart between them.**
A read-once-at-startup credential passes every unit test in this leg and fails
that step.

- **Source of truth**: the credential file on disk.
- **Rebuild trigger**: exactly one — the file's identity changing, detected by
  `stat`. A `stat` per lookup is cheap; a file read per lookup is not, and under
  DD6 every static asset is a lookup. Three things about this guard are load-
  bearing and easy to get subtly wrong:
  - **Use `st_mtime_ns`, not `st_mtime`.** A rotate can complete well inside one
    second's resolution.
  - **Size is a no-op for this format, not a second signal.** The credential is
    a fixed-length token, so every rotation produces a byte-identical size.
    Include it if you like as defense in depth against a future variable-length
    format, but do not reason as though the guard has two independent legs — its
    entire strength is `st_mtime_ns`, including on coarse-granularity
    filesystems, which are reachable here because `THE_ONE_DATA_DIR` is
    operator-overridable and may point at a removable volume.
  - **Compare with `!=`, never `>`.** `st_mtime_ns` is wall-clock, not
    monotonic. The natural-looking `if new_mtime > cached_mtime: rebuild`
    silently defeats the guard for exactly one request after a backward clock
    step — which is precisely the request the "maximum one request" bound exists
    to cover. An inequality check has no such failure mode.
- **Maximum acceptable staleness**: one request. The next authentication
  decision after a rotate must use the new credential.
- **Every mutation invalidates**: the rotate subcommand is the only writer, and
  it writes through `os.replace`, which changes both mtime and inode. There is
  no in-process mutation path that could bypass the trigger.
- Do **not** copy `encryption.py`'s `_encryptor_cache` pattern here — it caches
  by `data_dir` with no invalidation at all, which is correct for a key that
  only rotates through an in-process API and wrong for one rotated by a
  separate process.

Note the interaction this contract does *not* create: rotation invalidating
live sessions is a `gate-middleware` concern (the session must be bound to the
credential that established it). This leg's obligation is narrower — that a
reader sees the current credential. Do not build session logic here.

## Verification Steps

- New unit module: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_<credential-module>.py -x --timeout 30`
- Mode assertion: within that module, against a real file under `tmp_path` —
  `stat.S_IMODE(path.stat().st_mode) == 0o600`, under
  `@pytest.mark.skipif(os.name != "posix", ...)`.
- Atomicity of rotation needs **no** interruption test. Rotate is specified to
  reuse the same temp-file-plus-`os.replace` helper as creation, so the property
  is inherited from a path already covered by the `O_EXCL` structural check.
  Do not write a kill-mid-write test for it — it would be flaky and would prove
  nothing the helper's own coverage does not.
- No-chmod / `O_EXCL` structural assertion: monkeypatch `os.open` and `os.chmod`
  within the module under test, drive a creation, assert the flags and mode
  argument on the `os.open` call and that `os.chmod` was never called for the
  credential path.
- Cache contract: create a credential, read it, rewrite the file out-of-band
  with a different value (via `os.replace` from a temp file, as rotate does),
  read again in the *same process*, assert the new value is returned.
- Second-source seam: register an in-memory source, resolve one credential from
  each source through the same entry point, assert both yield an identified
  caller and that the callers name different sources.
- Rotate: `THE_ONE_DATA_DIR=<tmp> .venv/bin/the-one <rotate-subcommand>` —
  assert exit `0`, changed file content, mode still `0600`, and that the
  printed output does not contain the secret.
- CLI dispatch: assert the usage text lists the subcommand.
- Full gate: `make test-unit` green.

## Implementation Guidance

1. **Credential shape (DD1)** — the exact encoding is an acceptable variation
   per the flight spec. Pin these properties, not a format: parseable into
   `(identifier, secret)`; the prefix distinguishes credential *type* so a
   future admin or per-agent token is distinguishable at a glance; the
   identifier is safe to log; generation uses the `secrets` module, not
   `random`. Whatever format is chosen becomes a compatibility surface the
   moment it is written to disk — say so in the module docstring.

2. **File creation (DD2)** — mirror the connector-key rotation sequence in
   `the_one/interfaces/web/api.py`: write to a sibling temp file opened with
   `os.open(..., os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)`, `os.write`,
   `os.fsync`, `os.close`, then `os.replace` onto the canonical path. This
   gives both the no-world-readable-window property and atomicity, and rotate
   reuses it unchanged. Carry a comment explaining *why* `os.open` rather than
   `write_bytes` — a future reader will otherwise "simplify" it back.

3. **Identified caller (DD8)** — a small frozen dataclass. Give it a field
   naming the resolving source, so the seam test has something to assert on and
   so future logs can say which source authorized a caller.

4. **The lookup seam (DD8)** — the narrowest thing that satisfies the criterion:
   an ordered collection of sources, each answering "does this presented string
   resolve to a caller you own?", and one entry point that walks them. The file
   source is registered by default. The flight spec is emphatic that this
   accommodation is held to three items deliberately and warns of "speculative
   generality at one implementation" — resist adding scopes, expiry policy, or
   a registry API richer than register-and-resolve.

   Make the resolution entry point **synchronous**. `gate-middleware` will call
   it inline from an ASGI handler on every request; a stat plus an occasional
   read is sub-millisecond on local disk, and a sync call keeps that leg free of
   an executor hop it has no reason to pay for. Settling it here saves the next
   leg a decision.

5. **Rotate subcommand (DD9)** — a new `elif` in `cli_entry` following the
   established shape: import inside the branch (the existing branches all defer
   their imports, which keeps CLI startup cheap and matters for the frozen
   build), do the work, exit. Update the usage block. The subcommand name is an
   acceptable variation; make it unambiguous about *what* it rotates, since
   `encryption.key` rotation already exists elsewhere in the system and a bare
   `rotate` would be actively confusing.

6. **Do not print the secret on rotate.** No caller needs it from stdout — the
   launcher and the test harness read the file. Printing it would put the
   credential into shell history and terminal scrollback for no benefit.

## Edge Cases

- **Data directory does not exist** — call `Settings.ensure_dirs()` before
  creating. It is documented never to raise.
- **Credential file exists but is empty or malformed** — do not silently
  regenerate; that would mask a real problem and, at a bad moment, silently
  invalidate every live session. Raise with a message naming the path and
  telling the operator to run the rotate subcommand.
- **Credential file exists with wrong permissions** (e.g. restored from a
  backup, or copied by a tool that widened the mode) — this is a security
  finding, not a formatting nit. At minimum log a warning naming the path.
  Whether to refuse outright is the implementer's call; if refusing, the error
  must name the rotate subcommand as the fix.
- **Two processes race to create the credential on first launch** — the desktop
  shell can spawn a server while a test lane starts another. Be clear about the
  actual mechanism: `O_EXCL` guards the *temp* file, whose name is unique per
  attempt (the `api.py` precedent puts `secrets.token_hex(4)` in the suffix —
  keep that), so it never collides and never produces a "loser."
  `os.replace` onto the canonical path is last-write-wins and raises nothing.
  **No `FileExistsError` is ever raised anywhere in this design** — do not go
  looking for one to catch, and do not add an `O_EXCL` open on the canonical
  path, which is not part of the cited precedent and would break rotation. The
  correct handling is already implied by the Cache Contract: a writer must not
  trust the value it just wrote, but re-read through the same stat-guarded path
  as any other reader, so a racing process's winning write is picked up rather
  than shadowed by a stale in-memory copy.
- **Rotate against a data directory with no credential yet** — create one and
  report it as created, not replaced. Do not fail.
- **`repr()` in a traceback** — the whole point of the no-secret `repr` is that
  an unhandled exception in the middleware cannot dump the credential into a
  log. Make sure the dataclass does not get a default `repr` that undoes this.

## Files Affected

- `the_one/<credential-module>.py` — **new**. Credential shape, generation,
  exclusive-mode file creation, stat-guarded read, constant-time verification,
  identified-caller type, lookup seam.
- `the_one/main.py` — `cli_entry` gains a rotate branch; usage text updated.
- `tests/test_<credential-module>.py` — **new**. All criteria above.
- `ci/tasks/windows-tests.yml` — the new test module added to the curated
  Windows file list.
- `.github/workflows/test.yml` — the same addition to the `windows` job, which
  the Concourse task documents as its mirror.
- `packaging/windows/README.md` — **both** CLI-subcommand enumerations gain the
  new subcommand (the `dist/` listing comment and the installer prose).

## Citation Audit

Verified against the working tree at flight-baseline commit
`54d2d56`, on branch `flight/01-authenticated-local-api`:

| Citation | Status |
|----------|--------|
| `the_one/interfaces/web/api.py` — `os.open(..., O_EXCL, 0o600)` + fsync + `os.replace`, with the world-readable-window comment | Present, read in full |
| `the_one/encryption.py:Encryptor.rotate_key`, `get_encryptor` — `write_bytes` + `os.chmod`, and `_encryptor_cache` with no invalidation | Present, read in full |
| `the_one/main.py:cli_entry` — `sys.argv` dispatch, per-branch deferred imports, usage block | Present, read in full |
| `the_one/config.py:Settings` — `data_dir` via `default_factory`, `THE_ONE_` env prefix, `ensure_dirs()` documented never to raise | Present, read in full |
| `packaging/windows/README.md` — line enumerating the CLI subcommands | Present |
| `tests/CONVENTIONS.md` — auto asyncio mode, HOME-monkeypatch idiom | Present |
| `tests/test_frozen_entry.py` — checked as a possible `cli_entry` consumer; it mocks `cli_entry` wholesale and asserts nothing about dispatch branches | No impact from adding a subcommand |
| `tests/test_auth_posture_probe.py` — checked as a possible pinned-posture test | Out of scope: covers outbound MCP server classification, not this API |
| `tests/test_encryption.py:TestGetEncryptor.test_key_file_permissions` — `skipif(os.name != "posix")` guarding the identical `0o600` assertion | Present, verified after design review |
| `ci/tasks/windows-tests.yml` — MAINTENANCE comment plus explicit test-file list including `tests/test_encryption.py` | Present, verified after design review |
| `.github/workflows/test.yml` — `windows` job, documented mirror of the Concourse task's file list | Present, verified after design review |
| `packaging/windows/README.md` — two CLI enumerations, not one: the `dist/` listing comment and the installer prose | Present, verified after design review |

Line numbers are deliberately omitted from the citations above in favour of
symbol and content references, per the flight's durable-citation requirement.

## Designer Responses to Design Review

The design review (one cycle) returned *approve with changes*. All two
high-severity and three medium-severity issues were applied, along with both
non-blocking suggestions. Its two questions are answered here.

**On mission-criterion-7's evidence.** The reviewer is right that this leg's
in-memory-source unit test is, on its own, only half the claim — it proves a
second source *can* resolve, not that the request-gating logic is indifferent to
which source did. The other half is now a **forward commitment on
`gate-middleware`**: that leg's design must assert the middleware reaches the
credential module through this single resolution entry point with no
per-source branching, so the criterion is evidenced by both halves rather than
by one isolated seam test. Recorded in the flight log so it survives the gap
between leg designs.

**On whether `gate-middleware` influenced this module's API shape.** Partly, and
deliberately. The leg enforces nothing and touches no request path — that read is
correct and the Files Affected list bears it out. But two properties here exist
*because* of a known consumer: the resolution entry point is synchronous because
an ASGI handler will call it inline, and the Cache Contract exists because that
handler must notice an out-of-process rotation. Designing a primitive against its
known first caller is not scope leakage; building the caller here would be.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)

> **Note for this flight**: commit is deferred to the flight-end review gate
> (`/agentic-workflow` Phase 2d). The implementing Developer for this leg
> updates artifacts and signals `[HANDOFF:review-needed]` — it does **not**
> commit and does **not** signal `[COMPLETE:leg]`.
