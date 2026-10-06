"""``the-one doctor`` — frozen-runtime spawn diagnostic (M15 F5, DD5).

A small, LLM-free diagnostic that runs *inside* the (potentially frozen)
process and verifies the runtime seam end-to-end:

1. It builds the child env via ``_build_subprocess_env()`` — the exact env every
   real spawn path receives (allowlist-filtered + frozen-PATH-sanitized).
2. It **spawns a probe child** through that env (``cmd /c echo …`` on Windows,
   ``sh -c 'echo …'`` on POSIX) and checks the round-tripped output/exit — this
   is the load-bearing "a child process actually starts from the frozen app"
   check the whole mission gates on.
3. It probes for external runtimes (``node``/``npx``/``uv``/``uvx``/``python``)
   against the same sanitized PATH and reports presence with install guidance.

It prints a structured PASS/FAIL report (including an unambiguous
``child spawn: OK``/``child spawn: FAIL`` line) and exits non-zero on any
failure. The CI packaged-smoke reads exactly this exit code + stdout.

No agent loop, no LLM, no network.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from the_one.embeddings._backend import NORM_TOLERANCE, EmbeddingModelMissingError
from the_one.embeddings.local import EMBEDDING_DIM, EMBEDDING_WEIGHTS_FILENAME, LocalStaticBackend
from the_one.platform.env import _build_subprocess_env, is_frozen

# Probe marker echoed by the child and checked on the way back. Distinctive so a
# noisy environment can't produce a false positive.
_PROBE_MARKER = "the-one-doctor-ok"

# Runtimes we care about for the agent's spawn paths. Install-guidance messaging
# is reused from the MCP transport's hint table (single source of truth for the
# operator-facing "how to install" strings); the *probe* is written fresh here
# (a presence check against the sanitized PATH) — there is no existing reusable
# detector to extract.
_PROBED_RUNTIMES: tuple[str, ...] = ("node", "npx", "uv", "uvx", "python", "python3")


@dataclass
class ProbeResult:
    """Outcome of a single diagnostic probe."""

    name: str
    ok: bool
    detail: str


def _probe_child_spawn(env: dict[str, str]) -> ProbeResult:
    """Spawn a trivial child through the real spawn env and verify round-trip.

    Uses ``cmd /c echo`` on Windows and ``sh -c 'echo …'`` on POSIX. Resolves the
    shell to an absolute path against the (sanitized) PATH so a frozen, stripped
    GUI PATH doesn't cause a bare-name exec to fail spuriously.
    """
    path = env.get("PATH") or None
    if os.name == "nt":
        shell = shutil.which("cmd", path=path) or "cmd"
        argv = [shell, "/c", "echo", _PROBE_MARKER]
    else:
        shell = shutil.which("sh", path=path) or "/bin/sh"
        argv = [shell, "-c", f"echo {_PROBE_MARKER}"]

    try:
        completed = subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ProbeResult("child spawn", False, f"failed to spawn probe child: {exc}")

    if completed.returncode != 0:
        return ProbeResult(
            "child spawn",
            False,
            f"probe child exited {completed.returncode}: {completed.stderr.strip()!r}",
        )
    if _PROBE_MARKER not in completed.stdout:
        return ProbeResult(
            "child spawn",
            False,
            f"probe child produced unexpected output: {completed.stdout.strip()!r}",
        )
    return ProbeResult("child spawn", True, f"spawned via {argv[0]!r}, round-trip OK")


def detect_runtimes(env: dict[str, str]) -> list[ProbeResult]:
    """Probe for external runtimes on the sanitized PATH.

    A fresh presence check (``shutil.which`` against the cleaned PATH) — not a
    reusable detector, which does not exist. Missing runtimes are reported as
    informational (``ok=True``) with install guidance, NOT as hard failures: a
    host may legitimately lack ``node`` or ``uv``. The hard gate is the child
    spawn probe; runtime detection is advisory surface for the operator.
    """
    # Import the operator-facing install hints lazily to avoid pulling the MCP
    # transport module (and its heavier deps) into the doctor's import path
    # unless doctor actually runs.
    from the_one.mcp.transports.stdio import _RUNTIME_INSTALL_HINTS

    path = env.get("PATH") or None
    results: list[ProbeResult] = []
    for name in _PROBED_RUNTIMES:
        found = shutil.which(name, path=path)
        if found:
            results.append(ProbeResult(name, True, f"found at {found}"))
        else:
            hint = _RUNTIME_INSTALL_HINTS.get(name, f"`{name}` not found on PATH.")
            results.append(ProbeResult(name, True, f"not found — {hint}"))
    return results


def _probe_desktop_shell() -> ProbeResult:
    """Import the desktop-tray module (and its pystray/PIL deps) as a smoke check.

    On success prints ``desktop shell: OK`` — confirming pystray + Pillow are
    bundled and importable.  On ``ImportError`` the behaviour depends on context:

    - **Frozen** (``is_frozen()`` is True): the freeze MUST include the ``[gui]``
      extra, so a failed import is a hard gate → ``ok=False`` (``RESULT: FAIL``).
    - **Not frozen** (dev host): the ``[gui]`` extra may legitimately be absent;
      the line reads ``skipped`` and is informational only → ``ok=True``
      (``RESULT: PASS`` still prints).

    Either way this function never raises — all exceptions are caught.
    """
    try:
        import PIL  # noqa: F401
        import pystray  # noqa: F401

        import the_one.interfaces.desktop.tray  # noqa: F401 (import-only probe)

        return ProbeResult("desktop shell", True, "pystray + PIL importable")
    except ImportError as exc:
        if is_frozen():
            return ProbeResult(
                "desktop shell",
                False,
                f"import failed in frozen build (gui extra missing from bundle?): {exc}",
            )
        return ProbeResult(
            "desktop shell",
            True,
            "skipped (gui extra not installed)",
        )
    except Exception as exc:  # noqa: BLE001
        # Unexpected error: be safe, never crash doctor.
        if is_frozen():
            return ProbeResult("desktop shell", False, f"unexpected error: {exc}")
        return ProbeResult("desktop shell", True, f"skipped — unexpected error: {exc}")


# LLM provider modules registered via the lazy string-import loader in
# the_one/llm/registry.py:_try_load_builtin. PyInstaller cannot see those
# string __import__ calls, so each MUST be in the freeze's hiddenimports
# (packaging/windows/the-one.spec, via collect_submodules("the_one.llm")).
# Kept in sync with the loaders table in registry.py.
_LLM_PROVIDER_MODULES: tuple[str, ...] = (
    "the_one.llm.ollama_provider",
    "the_one.llm.anthropic_provider",
    "the_one.llm.anthropic_plan_provider",
    "the_one.llm.openai_provider",
    "the_one.llm.openrouter_provider",
    "the_one.llm.mock",
)


def _probe_llm_providers() -> ProbeResult:
    """Import every lazily-loaded LLM provider module as a smoke check.

    This is the gate for the M16 frozen-provider regression: provider modules
    are loaded via a string ``__import__`` in ``registry.py`` that PyInstaller's
    static analysis can't follow, so a missing hiddenimports entry silently
    tree-shakes them out of the bundle. The failure only surfaced at runtime
    when a user created an agent — ``get_provider()`` raised ``ModuleNotFoundError``,
    the WS handler crashed, and the chat dropped silently.

    - **Frozen**: all provider modules MUST import (the freeze installs
      ``[all-llms]`` and bundles ``the_one.llm``), so any failure is a hard gate
      → ``ok=False`` (``RESULT: FAIL``). The CI packaged-smoke reads this exit code.
    - **Not frozen** (dev host): optional SDK extras (openai/anthropic) may be
      absent, so import failures are informational only → ``ok=True``.

    Never raises — all exceptions are caught.
    """
    import importlib

    failures: list[str] = []
    for mod in _LLM_PROVIDER_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001 — report, never crash doctor
            failures.append(f"{mod} ({exc.__class__.__name__}: {exc})")

    if not failures:
        return ProbeResult(
            "llm providers",
            True,
            f"all {len(_LLM_PROVIDER_MODULES)} provider modules importable",
        )
    detail = "; ".join(failures)
    if is_frozen():
        return ProbeResult(
            "llm providers",
            False,
            f"provider module(s) missing from frozen bundle "
            f"(add to the-one.spec hiddenimports): {detail}",
        )
    return ProbeResult(
        "llm providers",
        True,
        f"skipped (extras not installed in dev): {detail}",
    )


# A model id that the bundled catalog seed (the_one/llm/data/model_catalog.json)
# is expected to carry — the default Anthropic model, which the seed maps to its
# native 1M window. Resolving a non-None window for it proves the seed data file
# is present and loadable; an empty result means the seed was not bundled.
_CATALOG_PROBE_MODEL = ("anthropic", "claude-sonnet-4-6")


def _probe_model_catalog() -> ProbeResult:
    """Resolve a known model window through the bundled catalog seed.

    Catches the seed-not-bundled regression (M16 F05 debrief): the seed is loaded
    via ``importlib.resources`` from ``the_one/llm/data/model_catalog.json``. If a
    freeze doesn't COLLECT that data file (PyInstaller spec ``datas``), the catalog
    resolves empty and every context window silently falls back to the class
    default. An import-only check (``_probe_llm_providers``) misses this because the
    seed is read lazily inside a swallowing try/except — the modules import fine
    with no seed present. This probe forces an actual resolution.

    - **Frozen**: the bundled seed MUST resolve the probe model → ``ok=False`` when
      it returns ``None`` (seed missing from the bundle) → ``RESULT: FAIL``. The CI
      packaged-smoke reads this exit code.
    - **Not frozen** (dev host): the source tree always carries the seed, so a
      non-resolving result is informational only → ``ok=True``.

    Never raises — all exceptions are caught.
    """
    provider, model = _CATALOG_PROBE_MODEL
    try:
        from the_one.llm.model_catalog import context_window_for

        window = context_window_for(provider, model)
    except Exception as exc:  # noqa: BLE001 — report, never crash doctor
        if is_frozen():
            return ProbeResult("model catalog", False, f"catalog probe raised: {exc}")
        return ProbeResult("model catalog", True, f"skipped — {exc}")

    if window:
        return ProbeResult("model catalog", True, f"seed resolves {model} -> {window}")
    if is_frozen():
        return ProbeResult(
            "model catalog",
            False,
            f"bundled seed did not resolve {model} (llm/data/model_catalog.json "
            "missing from the freeze — add to the-one.spec datas); context windows "
            "would silently fall back to class defaults",
        )
    return ProbeResult(
        "model catalog",
        True,
        f"skipped (seed did not resolve {model} on this host)",
    )


def _probe_interpreter() -> ProbeResult:
    """Verify a real external Python interpreter is resolvable.

    When frozen this exercises the ``resolve_python`` frozen branch; the
    actionable error (no interpreter / bad override) surfaces as a FAIL.
    """
    # Lazy import — interpreter pulls asyncio/signal; only needed when doctor runs.
    from the_one.platform.interpreter import FrozenInterpreterError, resolve_python

    try:
        interp = resolve_python()
    except FrozenInterpreterError as exc:
        return ProbeResult("python interpreter", False, str(exc))
    return ProbeResult("python interpreter", True, f"resolved to {interp}")


# ── Vector-store probe (M24 F01 L01, DD-3/DD-5/DD-6/DD-7; usearch-only since
# M24 F02 L06, DD-9) ──────────────────────────────────────────────────────
#
# usearch is the operator's DD-9 choice (flight-log.md, "DD-9 decision
# checkpoint (2026-09-15)") — the losing candidate's probe was removed in
# Leg 6. The probe loads the library directly — there is deliberately NO storage
# abstraction here (DD-6); the seam is Flight 2's work. What it gates is the
# packaging question: does usearch's NATIVE payload survive the PyInstaller
# freeze and still answer a real query? That is the same hazard class as the
# tree-shaken model-catalog seed above, one layer down at a loadable binary.
#
# Frozen-only gate (DD-7): the probe still always ATTEMPTS the real work —
# only the failure is downgraded when unfrozen.

# Tiny throwaway vector for the round-trips. Deliberately unrelated to the
# mission's real embedding width — these probes prove a library loads and
# answers, not anything about retrieval.
_VECTOR_PROBE_DIM = 4
_VECTOR_PROBE_VECTOR = (0.1, 0.2, 0.3, 0.4)
_VECTOR_PROBE_ROWID = 42
_VECTOR_PROBE_KEY = 7


def _vector_probe_outcome(name: str, reason: str) -> ProbeResult:
    """Frozen-only gating, shared by every probe (or probe half) that only
    hard-fails when frozen.

    Frozen → hard failure (``RESULT: FAIL``, read by both CI lanes). Not frozen
    → ``ok=True`` with a ``skipped —`` detail, matching the house pattern used by
    ``_probe_desktop_shell`` / ``_probe_llm_providers`` / ``_probe_model_catalog``
    / the vector-store probe (``_probe_usearch``) and, since Flight 4, the
    native round-trip half of ``_probe_file_watcher`` — whose import half
    does NOT route through here (it is unconditional on every host; see
    DD-9). The signature is already name-agnostic (``name``, ``reason``),
    which is what let this helper widen to a second caller with no shape
    change.
    """
    if is_frozen():
        return ProbeResult(name, False, reason)
    return ProbeResult(name, True, f"skipped — {reason}")


def _numkong_extension_state() -> str:
    """Describe whether numkong's own compiled extension loads in this process.

    Needed to disambiguate the two very different causes of ``numkong=no``:

    * the ``numkong._numkong`` extension is present but *unloadable* here —
      on Windows a ``.pyd`` whose dependent DLL cannot be resolved raises
      ``ImportError("DLL load failed while importing ...")``, and
      ``usearch/__init__.py`` swallows exactly that with a bare
      ``except ImportError: pass``.  That is a packaging defect we can fix.
    * the extension loads fine and ``usearch.compiled`` simply was not built
      against it.  That is a property of the upstream wheel — see
      ``_usearch_acceleration`` — and no packaging change can alter it.

    Reporting only the ``USES_NUMKONG`` flag cannot tell those apart, and the
    difference decides whether anyone should go looking for a missing DLL.

    Never raises.
    """
    try:
        from numkong import _numkong as _ext
    except Exception as exc:  # noqa: BLE001 — the message IS the diagnostic
        return f"numkong ext will not load ({exc.__class__.__name__}: {exc})"

    version = getattr(_ext, "__version__", "unknown")
    try:
        caps = _ext.get_capabilities()
        live = ",".join(n for n, on in caps.items() if on and n != "serial")
    except Exception as exc:  # noqa: BLE001
        live = f"capabilities unavailable ({exc.__class__.__name__})"
    return (
        f"numkong ext {version} loads fine [{live or 'serial only'}] — "
        "this usearch binary was built without numkong"
    )


def _usearch_acceleration() -> str:
    """Best-effort description of usearch's native acceleration state.

    ``usearch/__init__.py`` wraps its ``numkong`` import in a swallowing
    ``try/except ImportError``, so a frozen bundle missing ``numkong._numkong``
    still imports, still answers searches via dynamic dispatch, and would report
    a plain ``OK`` over a degraded bundle. Surfacing the flag in the doctor line
    makes that visible rather than fail-open (the DD-5 hazard, one layer down).

    ``USES_NUMKONG`` is baked in when the wheel is compiled, NOT decided at
    import time.  Verified against the published wheels: the Linux
    ``usearch.compiled`` carries undefined ``nk_*`` symbols (resolved from the
    numkong ``.so`` that ``__init__`` loads ``RTLD_GLOBAL``) and the full ISA
    name table; every ``win_amd64`` wheel from 2.16.0 through 2.26.2 has zero
    ``nk_`` references, no import of ``_numkong*.pyd``, an empty delay-import
    directory, no ``GetProcAddress``/``LoadLibrary``, and ``serial`` as its only
    ISA name.  The macOS wheel matches Linux, so Windows is the lone outlier.
    ``numkong=no, simd=serial`` on Windows is therefore an upstream wheel
    property, not a bundle defect — which is why the ``numkong=no`` branch
    appends the extension's own load state rather than leaving a reader to
    assume a DLL went missing.

    Never raises.
    """
    try:
        import usearch.compiled as _compiled

        uses_numkong = "yes" if getattr(_compiled, "USES_NUMKONG", 0) else "no"
        try:
            simd = _compiled.hardware_acceleration()
        except Exception:  # noqa: BLE001
            simd = "unknown"
        detail = f"numkong={uses_numkong}, simd={simd}"
        if uses_numkong == "no":
            detail = f"{detail}; {_numkong_extension_state()}"
        return detail
    except Exception as exc:  # noqa: BLE001
        return f"acceleration state unavailable ({exc.__class__.__name__})"


def _probe_usearch() -> ProbeResult:
    """Build an in-memory HNSW index, add one vector, and search it back.

    Three API facts the obvious implementation gets wrong, all verified:

    * ``Index()`` constructs fine with the default ``ndim=0`` but the first
      ``add`` then raises ``ValueError`` — pass ``ndim`` explicitly.
    * ``add``/``search`` assert ``isinstance(vectors, np.ndarray)`` — a plain
      Python list raises ``AssertionError: Expects a NumPy array``.
    * The index's default ``dtype`` is ``ScalarKind.BF16`` and keys come back as
      ``np.uint64`` — so assert on the KEY, never on the returned vector.

    Deliberately does NOT call ``usearch.sqlite_path()``: that path ships a
    ``BinaryManager`` which downloads ``usearch_sqlite.*`` from GitHub releases
    at runtime, and a probe that can satisfy itself by downloading is the same
    fail-open DD-5 wrote an invariant against.

    Never raises — all exceptions are caught.
    """
    name = "usearch"
    try:
        import numpy as np
        from usearch.index import Index

        vector = np.asarray(_VECTOR_PROBE_VECTOR, dtype=np.float32)
        index = Index(ndim=_VECTOR_PROBE_DIM)
        index.add(_VECTOR_PROBE_KEY, vector)
        matches = index.search(vector, 1)
        keys = [int(k) for k in matches.keys]
    except Exception as exc:  # noqa: BLE001 — report, never crash doctor
        return _vector_probe_outcome(name, f"{exc.__class__.__name__}: {exc}")

    accel = _usearch_acceleration()
    if _VECTOR_PROBE_KEY not in keys:
        return _vector_probe_outcome(
            name,
            f"index built but search returned keys {keys!r}, expected "
            f"{_VECTOR_PROBE_KEY} — the index is present but not answering "
            f"queries ({accel})",
        )
    return ProbeResult(
        name,
        True,
        f"HNSW round-trip returned key {_VECTOR_PROBE_KEY} ({accel})",
    )


# ── FTS5 probe (Flight 2 Leg 2, DD-11) ───────────────────────────────────
#
# Unlike the vector-store probe above, this one gates UNCONDITIONALLY:
# FTS5 is a mission constraint in every build (DD-11), not an optional extra
# whose presence legitimately varies by Python build the way
# `enable_load_extension` does — so it must never route through
# `_vector_probe_outcome`, and it never consults `is_frozen()`.

_FTS5_PROBE_TOKEN = "zq7xkdoctor"


def _probe_fts5() -> ProbeResult:
    """Build an in-memory FTS5 table, insert one row, and MATCH it back.

    Asserts the CONCRETE resolved rowid (1) rather than merely "no
    exception" — the ``report-what-you-got`` convention. Never raises; any
    failure (including a SQLite build compiled without FTS5 support) is
    reported as ``ok=False``, unconditionally, on every host.
    """
    name = "fts5"
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='porter unicode61')")
            conn.execute("INSERT INTO t (rowid, x) VALUES (1, ?)", (_FTS5_PROBE_TOKEN,))
            cur = conn.execute("SELECT rowid, bm25(t) FROM t WHERE t MATCH ?", (_FTS5_PROBE_TOKEN,))
            row = cur.fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — report, never crash doctor
        return ProbeResult(name, False, f"{exc.__class__.__name__}: {exc}")

    if row is None or row[0] != 1:
        return ProbeResult(
            name,
            False,
            f"index built but MATCH query returned {row!r}, expected rowid 1 "
            "— FTS5 is present but not answering queries",
        )
    return ProbeResult(
        name,
        True,
        f"fts5 available (SQLite {sqlite3.sqlite_version}); porter+unicode61 "
        f"MATCH round-trip returned rowid {row[0]}",
    )


# ── Embedding-model probe (M24 F01 L02, DD-1/DD-2/DD-5/DD-6/DD-7) ───────────
#
# The bundled float16 `potion-retrieval-32M` weights (the_one/embeddings/data/)
# are the mission's default embedding backend. This probe loads them FROM THE
# PACKAGED PATH and embeds a fixed string — it is the same hazard class as the
# model-catalog seed above, one layer out: a data tree shaken out of the bundle,
# or dropped by an incomplete package-data glob, fails silently at the point of
# use rather than at build time.
#
# M24 F02 L03: the embedding seam (`the_one.embeddings`) now sits between
# this probe and model2vec — the two DD-5 offline-load guards below moved
# into `the_one.embeddings.local.resolve_model_dir` so they protect every
# production load, not only this probe. This probe constructs a FRESH
# `LocalStaticBackend` (never the process singleton) and calls through the
# seam rather than around it.
#
# Unlike the vector-store probe above, this one gates UNCONDITIONALLY (DD-7):
# `model2vec` is a base dependency and the model is package data present in
# every checkout, so an unfrozen failure is a real defect — most usefully a
# missing package-data glob in a NON-EDITABLE wheel install, which a frozen-only
# gate would never catch. It must therefore never use `_vector_probe_outcome`.
#
# DD-5's probe invariant: the probe must be INCAPABLE of passing by download.
# model2vec's `_resolve_folder` returns the local directory only if it exists,
# then falls through to `snapshot_download()` — so on a networked worker a
# tree-shaken model would otherwise produce a PASSING probe that fetched the
# weights over the network. Two independent guards close that: the packaged path
# is asserted to resolve and exist BEFORE `from_pretrained` is called, and
# `HF_HUB_OFFLINE=1` is set in-process first so the hub fetch cannot succeed
# even if the path check were somehow bypassed.

# M24 F02 L03: the five underscored constants and `_force_hf_offline` that
# used to live here moved to `the_one.embeddings.local` (plain names,
# `EMBEDDING_DIM`, `EMBEDDING_WEIGHTS_FILENAME`, etc.) so production loads
# carry the same DD-5 offline guards this probe pioneered — this module now
# imports the plain names it still needs rather than owning them.
_EMBEDDING_PROBE_TEXT = "the-one doctor embedding probe"


def _peak_rss_bytes() -> tuple[int | None, str | None]:
    """Best-effort peak resident set size of this process, in bytes.

    DD-4's read path is `doctor`'s stdout and neither CI task measures memory,
    so the probe self-reports: that is what makes the 62 MiB asset's real
    footprint observable through the existing apparatus instead of a manual
    side-measurement. Flight 2 needs this figure for the float16-vs-int8
    vector-storage decision.

    Windows has no `resource` module, so the frozen bundle — the platform the
    number actually matters on — goes through `GetProcessMemoryInfo`. Both
    branches report a PEAK, not a current value, so the figure survives the
    model being garbage-collected before the line is printed.

    Returns ``(peak_bytes, None)`` on success or ``(None, reason)`` when no
    source is available — the reason is threaded into the probe's detail line
    so a Windows API failure is diagnosable from `doctor` stdout instead of a
    bare "unavailable". Never raises.
    """
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class _ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = _ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            # Without an explicit restype, GetCurrentProcess()'s HANDLE
            # pseudo-value (-1) is truncated by the default c_int return type
            # and re-widened incorrectly on a 64-bit process, so the memory
            # call below is handed an invalid handle and fails with
            # ERROR_INVALID_HANDLE (6) — verified on windows-worker. HANDLE
            # and BOOL restypes, and the getter's argtypes, fix this.
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.GetCurrentProcess.argtypes = []
            # K32GetProcessMemoryInfo lives in kernel32 on Windows 7+ and needs
            # no psapi.dll import; fall back to psapi for older/odd runtimes.
            getter = getattr(kernel32, "K32GetProcessMemoryInfo", None)
            if getter is None:
                getter = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
            getter.restype = wintypes.BOOL
            getter.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(_ProcessMemoryCounters),
                wintypes.DWORD,
            ]
            handle = kernel32.GetCurrentProcess()
            if not getter(handle, ctypes.byref(counters), counters.cb):
                last_error = ctypes.get_last_error()
                return None, f"GetProcessMemoryInfo failed, GetLastError={last_error}"
            return int(counters.PeakWorkingSetSize), None
        except Exception as exc:  # noqa: BLE001 — an advisory number, never a failure
            return None, f"{exc.__class__.__name__}: {exc}"

    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception as exc:  # noqa: BLE001
        return None, f"{exc.__class__.__name__}: {exc}"
    # ru_maxrss is KiB on Linux and BYTES on macOS/BSD — the one portability
    # trap in this call.
    peak_bytes = int(peak) if sys.platform == "darwin" else int(peak) * 1024
    return peak_bytes, None


def _probe_embedding_model() -> ProbeResult:
    """Construct a FRESH ``LocalStaticBackend`` and embed a probe string.

    Never calls ``get_embedding_backend()`` — the process-wide singleton
    (M24 F02 L03): the offline test that monkeypatches
    ``the_one.embeddings.local.EMBEDDING_MODEL_DIRNAME`` would otherwise
    race the singleton and pass or fail depending on test execution order.

    Asserts CONCRETE resolved values — dim, native dtype, norm, truncated
    count, weights byte size — rather than mere absence of exception, for
    the `_probe_model_catalog` reason: a capability that silently degrades
    is exactly what a probe exists to catch (``report-what-you-got``).

    The detail line carries the resolved directory AND ``model.safetensors``'s
    byte size, so a truncated file or a Git-LFS pointer left in place of the
    weights surfaces as a legible size mismatch rather than an opaque load
    error. It also carries this process's peak RSS (DD-4 read path; see
    ``_peak_rss_bytes``).

    Gates unconditionally (DD-7) — do NOT route failures through
    ``_vector_probe_outcome``.

    Never raises — an escaping exception would take down `doctor` and both CI
    gates for reasons unrelated to the model. The two DD-5 offline-load
    guards now live in ``LocalStaticBackend.load()`` /
    ``the_one.embeddings.local.resolve_model_dir`` — this probe calls
    through them rather than duplicating them.
    """
    name = "embedding model"
    try:
        backend = LocalStaticBackend.load()
    except EmbeddingModelMissingError as exc:
        return ProbeResult(name, False, str(exc))
    except Exception as exc:  # noqa: BLE001 — report, never crash doctor
        return ProbeResult(name, False, f"{exc.__class__.__name__}: {exc}")

    try:
        result = backend.embed([_EMBEDDING_PROBE_TEXT])
        vector = result.vectors[0]
        norm = float(np.linalg.norm(vector))
    except Exception as exc:  # noqa: BLE001 — report, never crash doctor
        return ProbeResult(
            name,
            False,
            f"{exc.__class__.__name__}: {exc} (path={backend.model_dir}, "
            f"{EMBEDDING_WEIGHTS_FILENAME}={backend.weights_bytes:,} bytes)",
        )

    peak, peak_unavailable_reason = _peak_rss_bytes()
    if peak is not None:
        rss = f"{peak / 1024 / 1024:.1f} MiB"
    else:
        rss = f"unavailable ({peak_unavailable_reason})"
    suffix = (
        f"({EMBEDDING_WEIGHTS_FILENAME}={backend.weights_bytes:,} bytes, "
        f"peak RSS {rss}) from {backend.model_dir}"
    )

    if backend.dim != EMBEDDING_DIM:
        return ProbeResult(
            name,
            False,
            f"embedded vector has {backend.dim} dimensions, expected {EMBEDDING_DIM} "
            f"— the packaged weights are not potion-retrieval-32M {suffix}",
        )
    # DD-1's measured float16-upcast tolerance — "unit-norm" here means
    # within NORM_TOLERANCE, never exact. This also catches the all-zeros
    # failure mode the previous line handled separately: a zero vector's
    # norm is trivially outside tolerance of 1.0.
    if abs(norm - 1.0) > NORM_TOLERANCE:
        return ProbeResult(
            name,
            False,
            f"model output is not unit-norm (norm {norm:.4f}) {suffix}",
        )
    if result.vectors.dtype != np.float32:
        return ProbeResult(
            name,
            False,
            f"embedding seam dtype is {result.vectors.dtype}, expected float32 {suffix}",
        )
    return ProbeResult(
        name,
        True,
        f"{backend.dim}-dim {backend.native_dtype} model -> float32 seam, norm "
        f"{norm:.4f}, truncated={result.truncated} {suffix}",
    )


# ── File-watcher probe (Flight 4 M24 F04 L01, DD-0/DD-9) ────────────────
#
# The Rust extension (`watchfiles._rust_notify`) is reached in the app
# today only through `uvicorn`'s reload supervisor, which `the-one serve`
# never uses, so no frozen build to date has proven it loads.
# `pyproject.toml` now declares `watchfiles` directly (DD-11); this probe
# proves the import AND, when frozen, a real round-trip:
#
# (1) `import watchfiles` and reference `watchfiles.watch` — a failure
#     here is `ok=False` on EVERY host, never routed through
#     `_vector_probe_outcome` (which always downgrades an unfrozen
#     failure to `ok=True`): from this flight the app imports the module
#     at startup everywhere, so a missing or unloadable extension is a
#     defect wherever it happens.
# (2) a real native change-notification round-trip on a fresh temporary
#     directory — frozen-only per DD-9 (the house "always attempt,
#     downgrade only the failure" rule, via `_vector_probe_outcome`).
#
# Every `watchfiles.watch` keyword below is passed explicitly (DD-0) — no
# library or environment default is inherited. `force_polling=False` and
# `ignore_permission_denied=False` are pinned; this probe never needs
# DD-0's two-step subscribe (a fresh `TemporaryDirectory` is always
# readable by the process that created it).

_FILE_WATCHER_DEADLINE_FROZEN_SECONDS = 10.0
_FILE_WATCHER_DEADLINE_UNFROZEN_SECONDS = 2.0


def _import_watchfiles():
    """Seam the tests monkeypatch to simulate an import failure without
    uninstalling the real package.

    `tests/test_doctor.py`'s targeted probe tests call THIS module's
    top-level `_probe_file_watcher` directly (the `_probe_usearch`
    precedent) — `run_doctor`'s autouse stub applies only when `doctor`
    resolves its own module global, which the targeted tests bypass by
    importing the symbol.
    """
    import watchfiles

    return watchfiles


def _probe_file_watcher() -> ProbeResult:
    """Import `watchfiles` (unconditional gate) and, when frozen, prove a
    real native change-notification round-trip on a fresh temporary
    directory.

    Writes a fresh file named `probe-<n>.txt` (`n` incrementing) after
    EACH timeout yield inside the loop that consumes them (Architect,
    cycle 2) — the generator body, and so the Rust notifier, does not
    exist until the first `next()`, so a single early write from a helper
    thread would be lost. Iterates until a non-empty change set arrives or
    an overall deadline passes (`_FILE_WATCHER_DEADLINE_FROZEN_SECONDS` /
    `_FILE_WATCHER_DEADLINE_UNFROZEN_SECONDS`) — never "the first yield
    must be non-empty", which on a loaded frozen CI runner would fail the
    installer build for a scheduling hiccup; `watch`'s own default
    `debounce` alone would put the first real yield up to 1.6 s after the
    write, so this probe pins a 200 ms `debounce` and `rust_timeout=250`.
    The generator is closed explicitly in a `finally`.

    A round-trip failure (exception, or the deadline passing with nothing
    delivered) is routed through `_vector_probe_outcome` with
    `f"import OK; round-trip: {reason}"` as the reason — `skipped — `
    unfrozen, a hard `FAIL` frozen.

    Never raises.
    """
    name = "file watcher"
    try:
        watchfiles = _import_watchfiles()
        # Reference `.watch` explicitly — AC-6: a partially-broken module
        # object (the extension present but the attribute missing) must
        # surface here, not only at the first call below.
        _ = watchfiles.watch
    except Exception as exc:  # noqa: BLE001 — report, never crash doctor
        return ProbeResult(
            name, False, f"watchfiles import failed: {exc.__class__.__name__}: {exc}"
        )

    deadline_seconds = (
        _FILE_WATCHER_DEADLINE_FROZEN_SECONDS
        if is_frozen()
        else _FILE_WATCHER_DEADLINE_UNFROZEN_SECONDS
    )

    try:
        with tempfile.TemporaryDirectory() as tmp:
            gen = watchfiles.watch(
                tmp,
                watch_filter=None,
                debounce=200,
                step=50,
                rust_timeout=250,
                yield_on_timeout=True,
                force_polling=False,
                ignore_permission_denied=False,
                raise_interrupt=False,
                debug=False,
                poll_delay_ms=300,
                recursive=True,
            )
            start = time.monotonic()
            n = 0
            try:
                for changes in gen:
                    if changes:
                        return ProbeResult(name, True, "native change notification round-trip OK")
                    if time.monotonic() - start > deadline_seconds:
                        return _vector_probe_outcome(
                            name,
                            "import OK; round-trip: no change delivered within "
                            f"{deadline_seconds:.0f}s",
                        )
                    n += 1
                    (Path(tmp) / f"probe-{n}.txt").write_text("x")
            finally:
                gen.close()
    except Exception as exc:  # noqa: BLE001 — report, never crash doctor
        return _vector_probe_outcome(
            name, f"import OK; round-trip: {exc.__class__.__name__}: {exc}"
        )

    # The consuming loop itself checks the deadline on every iteration, so
    # this is unreachable in practice — kept as a defensive fallback.
    return _vector_probe_outcome(name, "import OK; round-trip: no change delivered")


def _probe_window_chrome() -> ProbeResult:
    """Prove the DWM window-chrome path loads (M25 F5 L3, flight DD8).

    Unconditional (not frozen-only). Off Windows it reports a skip. On Windows it
    loads ``dwmapi`` and calls ``DwmSetWindowAttribute`` with a NULL window handle
    (which is expected to return an error HRESULT, proving the entry point is
    callable), then reports whether this build supports caption colours (22000+)
    or dark mode only. Never raises; the detail is ASCII only (cp1252 CI pipes).
    """
    name = "window chrome"
    if sys.platform != "win32":
        return ProbeResult(name, True, "skipped (not Windows)")
    try:
        import ctypes

        from the_one.interfaces.desktop import chrome

        dwmapi = ctypes.windll.dwmapi
        func = dwmapi.DwmSetWindowAttribute
        value = ctypes.c_int(0)
        hr = int(func(None, 35, ctypes.byref(value), 4)) & 0xFFFFFFFF
        build = chrome.windows_build()
        if build is not None and build >= chrome.COLOR_ATTRS_MIN_BUILD:
            return ProbeResult(
                name, True, f"caption colours supported (build {build}, probe 0x{hr:08X})"
            )
        return ProbeResult(name, True, f"dark mode only (build {build}, probe 0x{hr:08X})")
    except Exception as exc:
        detail = f"dwmapi unavailable: {exc.__class__.__name__}: {exc}"
        return ProbeResult(name, False, detail.encode("ascii", "replace").decode("ascii"))


def run_doctor(out=None) -> int:
    """Run all diagnostics, print a structured report, return an exit code.

    Returns 0 when every gate passes — child spawn, python interpreter, desktop
    shell, llm providers, model catalog, usearch, fts5, embedding
    model, file watcher and window chrome — and non-zero otherwise. Of those **ten**, four
    are frozen-only (desktop shell, llm providers, model catalog, usearch): on
    a dev host they downgrade a failure to an informational ``skipped`` line
    rather than failing the run. The other six — child spawn, python
    interpreter, **fts5**, **embedding model**, **file watcher**'s import
    check and **window chrome** (skipped off Windows) — gate
    unconditionally; file watcher is the one hybrid gate (Flight 4 DD-9):
    its import half gates unconditionally, on every host, but its
    native round-trip half gates only when frozen, downgrading through the
    same ``_vector_probe_outcome`` helper the four frozen-only gates use.
    fts5 gates unconditionally per DD-11 (a mission constraint in every
    build, not an optional extra). The embedding gate is unconditional by
    design (M24 F01 DD-7): model2vec is a base dependency and the weights are
    package data present in every checkout, so a host failure is a real
    defect — most usefully a missing package-data glob in a non-editable
    wheel install, which a frozen-only gate would never catch. Runtime
    detection lines are advisory and never by themselves fail the run.
    ``out`` defaults to ``sys.stdout``; tests pass a buffer.
    """
    stream = out if out is not None else sys.stdout

    def emit(line: str) -> None:
        # A diagnostic must never die on its own output. Build 606620 (M24 F02
        # L06, AC-15) crashed the frozen Windows doctor mid-run: both CI lanes
        # pipe stdout, which Windows resolves to the cp1252 codec, and a probe
        # detail containing a non-cp1252 character (U+2192 "→") raised
        # UnicodeEncodeError and killed the process before RESULT could print.
        # Try the plain print first so UTF-8 streams (tests, real consoles)
        # stay byte-identical to today; only fall back to a replaced re-emit
        # when the stream's encoding can't represent the line.
        try:
            print(line, file=stream)
        except UnicodeEncodeError:
            encoding = getattr(stream, "encoding", None) or "ascii"
            safe_line = line.encode(encoding, errors="replace").decode(encoding)
            print(safe_line, file=stream)

    env = _build_subprocess_env()

    emit("the-one doctor — frozen-runtime spawn diagnostic")
    emit(f"  frozen: {is_frozen()}")
    emit(f"  PATH: {env.get('PATH', '')!r}")
    emit("")

    # Load-bearing gates.
    spawn = _probe_child_spawn(env)
    interp = _probe_interpreter()
    # Desktop-shell probe: gate only when frozen (frozen build must include [gui]);
    # on a dev host the [gui] extra may legitimately be absent → informational only.
    desktop = _probe_desktop_shell()
    # LLM-provider gate: like desktop-shell, only a hard gate when frozen
    # (the freeze must bundle every lazily-imported provider module).
    llm_providers = _probe_llm_providers()
    # Model-catalog gate: like the provider gate, only hard when frozen — the
    # freeze must bundle the seed data file, not just the llm modules.
    model_catalog = _probe_model_catalog()
    # Vector-store gate (M24 F01 L01; usearch-only since M24 F02 L06, DD-9):
    # frozen-only per DD-7 — usearch's native payload must survive the freeze
    # and still answer a real query. Both CI lanes grep this name verbatim.
    usearch_probe = _probe_usearch()
    # FTS5 gate (Flight 2 Leg 2, DD-11): UNCONDITIONAL — FTS5 is a mission
    # constraint in every build, not an optional extra like the vector-store
    # gate above. Both CI lanes grep this name verbatim.
    fts5_probe = _probe_fts5()
    # Embedding-model gate (M24 F01 L02): UNCONDITIONAL per DD-7 — unlike the
    # vector-store gate above, this one fails the run on a dev host too. Both
    # CI lanes grep this name verbatim, so keep it stable.
    embedding_model = _probe_embedding_model()
    # File-watcher gate (Flight 4 M24 F04 L01, DD-0/DD-9): the one hybrid
    # gate — its `import watchfiles` half is UNCONDITIONAL (every host), its
    # native round-trip half is frozen-only. Both CI lanes grep this name
    # verbatim.
    file_watcher = _probe_file_watcher()
    # Window-chrome gate (M25 F5 L3, DD8): unconditional; skipped off Windows.
    # Both CI lanes grep this name verbatim.
    window_chrome = _probe_window_chrome()
    gates = [
        spawn,
        interp,
        desktop,
        llm_providers,
        model_catalog,
        usearch_probe,
        fts5_probe,
        embedding_model,
        file_watcher,
        window_chrome,
    ]

    for res in gates:
        status = "OK" if res.ok else "FAIL"
        emit(f"  {res.name}: {status} — {res.detail}")

    emit("")
    emit("  runtimes:")
    for res in detect_runtimes(env):
        emit(f"    {res.name}: {res.detail}")

    emit("")
    all_ok = all(g.ok for g in gates)
    emit(f"RESULT: {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1
