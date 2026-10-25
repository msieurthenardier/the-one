"""Tests for ``the-one doctor`` (M15 F5, DD5) — ``the_one.diagnostics``.

The doctor must (a) spawn a probe child through the real spawn env, (b) detect
runtimes, (c) print a structured PASS/FAIL with a ``child spawn: OK``/``FAIL``
line, and (d) exit non-zero on failure. Runs LLM-free. These tests exercise the
host (non-frozen) path — the dev-loop / CI-host case the leg explicitly requires
to pass before a frozen binary exists — plus simulated-failure paths.
"""

from __future__ import annotations

import io
import re
import sqlite3
import sys
import time
import types

import pytest

from the_one import diagnostics
from the_one.diagnostics import (
    ProbeResult,
    _numkong_extension_state,
    _probe_desktop_shell,
    _probe_file_watcher,
    _probe_fts5,
    _probe_llm_providers,
    _probe_model_catalog,
    _probe_usearch,
    _usearch_acceleration,
    detect_runtimes,
    run_doctor,
)


# The `embedding model` gate is UNCONDITIONAL (M24 F01 DD-7), so without this
# every ``run_doctor(`` call in this file — there are 21, across 10 classes —
# would load the 62 MiB bundled potion-retrieval-32M weights. Patching a single
# "host test" would leave twenty still paying for it.
#
# Function-scoped on purpose. A module-scoped fixture cannot request the
# function-scoped ``monkeypatch`` (pytest raises ScopeMismatch) and would need a
# hand-managed ``pytest.MonkeyPatch()``, for which this repo has no precedent.
# What is being avoided is the model load, not the ``setattr``.
#
# pytest offers no opt-out from an autouse fixture, so the dedicated REAL-load
# test does not live here — it lives in ``tests/test_doctor_embedding_model.py``,
# which is the only host-side proof that the real asset loads and therefore must
# never itself be mocked or skipped.
@pytest.fixture(autouse=True)
def _stub_embedding_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        diagnostics,
        "_probe_embedding_model",
        lambda: ProbeResult(
            "embedding model",
            True,
            "stubbed by the tests/test_doctor.py autouse fixture (real load is "
            "covered by tests/test_doctor_embedding_model.py)",
        ),
    )


# The `file watcher` gate's round-trip half costs up to
# `_FILE_WATCHER_DEADLINE_UNFROZEN_SECONDS` (2 s) per call on a host where the
# self-probe doesn't deliver quickly — and there are 21 `run_doctor(` call
# sites in this file (the same count the embedding-probe fixture above cites).
# Stubbed here for the same reason: a single "host test" stub would leave the
# other twenty paying for it. `TestProbeFileWatcher`'s targeted tests below
# call the module-top-imported `_probe_file_watcher` directly (the
# `_probe_usearch` precedent — `monkeypatch.setattr(diagnostics, …)` does not
# rebind a name a test file already imported by value), so this autouse stub
# does not apply to them.
@pytest.fixture(autouse=True)
def _stub_file_watcher_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        diagnostics,
        "_probe_file_watcher",
        lambda: ProbeResult(
            "file watcher",
            True,
            "stubbed by the tests/test_doctor.py autouse fixture (real "
            "round-trip covered by TestProbeFileWatcher below)",
        ),
    )


class TestRunDoctorHost:
    def test_passes_on_host_with_child_spawn_ok(self) -> None:
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code == 0
        assert "child spawn: OK" in text
        assert "RESULT: PASS" in text
        # Runtime-detection summary is present.
        assert "runtimes:" in text

    def test_sqlite_vec_gate_is_gone(self) -> None:
        """M24 F02 L06 (DD-9): `sqlite-vec` was removed from the closure —
        the by-name inverse of the `usearch:`/`fts5:` line-present tests,
        so a stray re-add of the removed gate is caught."""
        buf = io.StringIO()
        run_doctor(out=buf)
        assert "sqlite-vec:" not in buf.getvalue()

    def test_no_llm_or_network_import(self) -> None:
        # The module must not require an agent loop. Smoke: importing and running
        # doctor doesn't pull a provider/agent at module top — just confirm the
        # public surface is the small diagnostic set.
        assert hasattr(diagnostics, "run_doctor")
        assert hasattr(diagnostics, "detect_runtimes")


class TestRunDoctorFailures:
    def test_nonzero_when_child_spawn_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            diagnostics,
            "_probe_child_spawn",
            lambda env: ProbeResult("child spawn", False, "simulated unspawnable child"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "child spawn: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_nonzero_when_interpreter_unresolvable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            diagnostics,
            "_probe_interpreter",
            lambda: ProbeResult("python interpreter", False, "no interpreter (simulated)"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        assert code != 0
        assert "python interpreter: FAIL" in buf.getvalue()


class TestDetectRuntimes:
    def test_missing_runtime_is_advisory_not_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(diagnostics.shutil, "which", lambda name, path=None: None)
        results = detect_runtimes({"PATH": "/usr/bin"})
        # All reported, none are hard failures (advisory surface).
        assert results
        assert all(r.ok for r in results)
        # Missing runtimes carry install guidance.
        assert any("not found" in r.detail for r in results)

    def test_present_runtime_reports_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(diagnostics.shutil, "which", lambda name, path=None: f"/usr/bin/{name}")
        results = detect_runtimes({"PATH": "/usr/bin"})
        assert all(r.ok for r in results)
        assert any("found at /usr/bin/" in r.detail for r in results)


class TestDispatch:
    def test_main_doctor_branch_exits_with_doctor_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import the_one.main as main_mod

        monkeypatch.setattr(main_mod.sys, "argv", ["the-one", "doctor"])
        monkeypatch.setattr(diagnostics, "run_doctor", lambda: 0)
        with pytest.raises(SystemExit) as exc:
            main_mod.cli_entry()
        assert exc.value.code == 0

    def test_main_doctor_branch_propagates_failure_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import the_one.main as main_mod

        monkeypatch.setattr(main_mod.sys, "argv", ["the-one", "doctor"])
        monkeypatch.setattr(diagnostics, "run_doctor", lambda: 3)
        with pytest.raises(SystemExit) as exc:
            main_mod.cli_entry()
        assert exc.value.code == 3


# ── Desktop-shell doctor probe (M15 F6 L5) ───────────────────────────────────


def _make_stub_module(name: str) -> types.ModuleType:
    """Return a trivial stub module for sys.modules injection."""
    mod = types.ModuleType(name)
    return mod


class TestProbeDesktopShell:
    """Unit tests for the new ``_probe_desktop_shell`` doctor line."""

    def test_ok_path_when_imports_present(self) -> None:
        """When the desktop tray module and its deps are importable → ok=True, 'OK' in output."""
        # Inject stubs into sys.modules so the lazy imports inside
        # _probe_desktop_shell succeed without a real [gui] install.
        stubs = {
            "pystray": _make_stub_module("pystray"),
            "PIL": _make_stub_module("PIL"),
        }
        # the_one.interfaces.desktop.tray is a real module; ensure it's importable
        # (it only lazily imports pystray/PIL itself, so no stub needed for the
        # tray module on this path — the real module imports cleanly).
        with pytest.MonkeyPatch.context() as mp:
            for name, mod in stubs.items():
                mp.setitem(sys.modules, name, mod)
            result = _probe_desktop_shell()
        assert result.ok is True
        assert "OK" in result.detail or "importable" in result.detail

    def test_skip_path_when_import_absent_not_frozen(self) -> None:
        """When pystray is missing on a non-frozen host → ok=True (informational skip)."""
        with pytest.MonkeyPatch.context() as mp:
            # Remove pystray from sys.modules so the import raises ImportError.
            mp.delitem(sys.modules, "pystray", raising=False)
            # Ensure is_frozen() returns False.
            mp.setattr(diagnostics, "is_frozen", lambda: False)
            # Make pystray unimportable by inserting a bad entry that will
            # be restored after the context.  We shadow via a None sentinel
            # which Python treats as "module not found" when __import__ hits it.
            mp.setitem(sys.modules, "pystray", None)  # type: ignore[arg-type]
            result = _probe_desktop_shell()
        assert result.ok is True
        assert "skipped" in result.detail

    def test_skip_keeps_result_pass_in_run_doctor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-frozen skip → RESULT: PASS in the full doctor output."""
        monkeypatch.setattr(
            diagnostics,
            "_probe_desktop_shell",
            lambda: ProbeResult("desktop shell", True, "skipped (gui extra not installed)"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code == 0
        assert "RESULT: PASS" in text
        assert "desktop shell: OK" in text

    def test_frozen_import_fail_is_result_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Frozen build with missing pystray → ok=False → RESULT: FAIL."""
        # Stub _probe_desktop_shell to return the frozen-fail outcome and verify
        # run_doctor promotes it to RESULT: FAIL.
        monkeypatch.setattr(
            diagnostics,
            "_probe_desktop_shell",
            lambda: ProbeResult(
                "desktop shell",
                False,
                "import failed in frozen build (gui extra missing from bundle?)",
            ),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "desktop shell: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_doctor_desktop_line_present_in_output(self) -> None:
        """The desktop shell line appears in run_doctor output on this host."""
        buf = io.StringIO()
        run_doctor(out=buf)
        text = buf.getvalue()
        assert "desktop shell:" in text


class TestProbeLLMProviders:
    """Unit tests for the ``_probe_llm_providers`` doctor line (M16 frozen-
    provider regression gate)."""

    def test_ok_when_all_modules_importable(self) -> None:
        """On a dev host with the source tree present, all provider modules import."""
        result = _probe_llm_providers()
        assert result.ok is True
        assert "importable" in result.detail

    def test_frozen_fail_when_module_missing(self) -> None:
        """Frozen build missing a provider module → ok=False, actionable detail.

        Simulates the exact regression: a provider module tree-shaken out of the
        frozen bundle. A ``None`` sentinel in sys.modules makes the import raise
        ModuleNotFoundError, mirroring the absent-from-bundle condition.
        """
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: True)
            mp.setitem(sys.modules, "the_one.llm.ollama_provider", None)  # type: ignore[arg-type]
            result = _probe_llm_providers()
        assert result.ok is False
        assert "the_one.llm.ollama_provider" in result.detail
        assert "hiddenimports" in result.detail

    def test_nonfrozen_missing_is_informational_skip(self) -> None:
        """Missing provider on a non-frozen host → ok=True (extras may be absent)."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: False)
            mp.setitem(sys.modules, "the_one.llm.anthropic_provider", None)  # type: ignore[arg-type]
            result = _probe_llm_providers()
        assert result.ok is True
        assert "skipped" in result.detail

    def test_frozen_fail_promotes_result_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A frozen provider-probe failure promotes the whole run to RESULT: FAIL."""
        monkeypatch.setattr(
            diagnostics,
            "_probe_llm_providers",
            lambda: ProbeResult(
                "llm providers",
                False,
                "provider module(s) missing from frozen bundle",
            ),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "llm providers: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_doctor_llm_line_present_in_output(self) -> None:
        """The llm providers line appears in run_doctor output on this host."""
        buf = io.StringIO()
        run_doctor(out=buf)
        assert "llm providers:" in buf.getvalue()


class TestProbeModelCatalog:
    """Unit tests for the ``_probe_model_catalog`` doctor line — the M16 F05
    frozen-seed regression gate (seed data file tree-shaken from the bundle)."""

    def test_ok_when_seed_resolves(self) -> None:
        """On a dev host the bundled seed resolves the probe model to a window."""
        result = _probe_model_catalog()
        assert result.ok is True
        assert "->" in result.detail  # "seed resolves ... -> <window>"

    def test_frozen_fail_when_seed_missing(self) -> None:
        """Frozen build where the seed doesn't resolve (None) → ok=False, actionable.

        Simulates the bundle missing llm/data/model_catalog.json: the loader
        fail-opens to an empty catalog, so context_window_for returns None.
        """
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: True)
            mp.setattr(
                "the_one.llm.model_catalog.context_window_for",
                lambda provider, model: None,
            )
            result = _probe_model_catalog()
        assert result.ok is False
        assert "the-one.spec datas" in result.detail

    def test_nonfrozen_missing_is_informational_skip(self) -> None:
        """Seed not resolving on a non-frozen host → ok=True (informational)."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: False)
            mp.setattr(
                "the_one.llm.model_catalog.context_window_for",
                lambda provider, model: None,
            )
            result = _probe_model_catalog()
        assert result.ok is True
        assert "skipped" in result.detail

    def test_frozen_fail_promotes_result_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A frozen catalog-probe failure promotes the whole run to RESULT: FAIL."""
        monkeypatch.setattr(
            diagnostics,
            "_probe_model_catalog",
            lambda: ProbeResult("model catalog", False, "bundled seed did not resolve"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "model catalog: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_doctor_catalog_line_present_in_output(self) -> None:
        """The model catalog line appears in run_doctor output on this host."""
        buf = io.StringIO()
        run_doctor(out=buf)
        assert "model catalog:" in buf.getvalue()


# ── Vector-store doctor probe (M24 F01 L01; usearch-only since M24 F02 L06,
# DD-9) ───────────────────────────────────────────────────────────────────
#
# Frozen-only gate per DD-7: it ALWAYS attempts the real work, and downgrades
# only a *failure* to an informational `skipped —` line when the process is
# not frozen. Must be incapable of raising — an escaping exception would take
# down `doctor` entirely and break the CI gate for reasons unrelated to the
# library under test.


class _StubMatches:
    """usearch ``Matches`` stand-in exposing only what the probe reads."""

    def __init__(self, keys) -> None:
        self.keys = keys


class _StubIndex:
    """usearch ``Index`` stand-in whose search returns a caller-chosen key set."""

    def __init__(self, keys) -> None:
        self._keys = keys

    def add(self, key, vector) -> None:  # noqa: D102
        return None

    def search(self, vector, count) -> _StubMatches:  # noqa: D102
        return _StubMatches(self._keys)


class TestProbeUsearch:
    """Unit tests for the ``usearch`` doctor line."""

    def test_ok_when_index_round_trips(self) -> None:
        """Real in-memory HNSW index returns the key it was given."""
        result = _probe_usearch()
        assert result.ok is True
        assert "key 7" in result.detail

    def test_detail_surfaces_numkong_state(self) -> None:
        """The detail must expose whether numkong loaded — usearch swallows that
        ImportError, so a degraded bundle would otherwise report a plain OK."""
        result = _probe_usearch()
        assert "numkong=" in result.detail

    def test_frozen_fail_when_the_native_core_is_missing(self) -> None:
        """Frozen bundle where usearch cannot build an index → ok=False."""

        def _boom(*args, **kwargs):
            raise ImportError("No module named 'usearch.compiled' (simulated)")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: True)
            mp.setattr("usearch.index.Index", _boom)
            result = _probe_usearch()
        assert result.ok is False
        assert "ImportError" in result.detail

    def test_nonfrozen_failure_is_informational_skip(self) -> None:
        """Same failure on a dev host → ok=True with a `skipped —` detail (DD-7)."""

        def _boom(*args, **kwargs):
            raise ImportError("simulated missing usearch.compiled")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: False)
            mp.setattr("usearch.index.Index", _boom)
            result = _probe_usearch()
        assert result.ok is True
        assert result.detail.startswith("skipped — ")

    def test_frozen_fail_when_search_misses_the_known_key(self) -> None:
        """An index that answers with the wrong key is a failure, not a pass."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: True)
            mp.setattr("usearch.index.Index", lambda **kwargs: _StubIndex([999]))
            result = _probe_usearch()
        assert result.ok is False
        assert "expected 7" in result.detail

    def test_probe_never_raises_and_doctor_still_exits_with_a_code(self) -> None:
        """A library that raises must surface as a FAIL line, never propagate."""

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated native crash")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: True)
            mp.setattr("usearch.index.Index", _boom)
            buf = io.StringIO()
            code = run_doctor(out=buf)
        text = buf.getvalue()
        assert isinstance(code, int)
        assert code != 0
        assert "usearch: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_frozen_fail_promotes_result_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A frozen usearch failure promotes the whole run to RESULT: FAIL."""
        monkeypatch.setattr(
            diagnostics,
            "_probe_usearch",
            lambda: ProbeResult("usearch", False, "usearch.compiled missing from the bundle"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "usearch: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_doctor_usearch_line_present_in_output(self) -> None:
        """The usearch line — which both CI lanes grep by name — is emitted."""
        buf = io.StringIO()
        run_doctor(out=buf)
        assert "usearch:" in buf.getvalue()


class _Fts5UnavailableConnection:
    """Real sqlite3 connection whose ``CREATE VIRTUAL TABLE ... fts5(...)``
    call raises, simulating a SQLite build compiled without FTS5 support.
    A connection-wrapping technique in the same style as the stub classes
    ``TestProbeUsearch`` uses above."""

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real

    def __getattr__(self, name: str):
        return getattr(self._real, name)

    def execute(self, sql: str, params=()):
        if "VIRTUAL TABLE" in sql:
            raise sqlite3.OperationalError("no such module: fts5 (simulated)")
        return self._real.execute(sql, params)


class TestProbeFts5:
    """Unit tests for the ``fts5`` doctor line (Flight 2 Leg 2, DD-11).

    Unlike the vector-store probe, ``_probe_fts5`` gates
    UNCONDITIONALLY — it never routes through ``_vector_probe_outcome`` and
    never consults ``is_frozen()`` (FTS5 is a mission constraint in every
    build, not an optional extra).
    """

    def test_ok_with_sqlite_version_and_matched_rowid_in_detail(self) -> None:
        result = _probe_fts5()
        assert result.ok is True
        assert "rowid 1" in result.detail
        assert f"SQLite {sqlite3.sqlite_version}" in result.detail

    def test_fails_when_the_connection_cannot_create_the_virtual_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_connect = sqlite3.connect
        fake_module = types.SimpleNamespace(
            connect=lambda *a, **k: _Fts5UnavailableConnection(real_connect(*a, **k)),
            sqlite_version=sqlite3.sqlite_version,
        )
        monkeypatch.setattr(diagnostics, "sqlite3", fake_module)
        result = _probe_fts5()
        assert result.ok is False
        assert "OperationalError" in result.detail

    def test_failure_is_unconditional_regardless_of_is_frozen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_connect = sqlite3.connect
        fake_module = types.SimpleNamespace(
            connect=lambda *a, **k: _Fts5UnavailableConnection(real_connect(*a, **k)),
            sqlite_version=sqlite3.sqlite_version,
        )
        monkeypatch.setattr(diagnostics, "sqlite3", fake_module)
        for frozen in (True, False):
            monkeypatch.setattr(diagnostics, "is_frozen", lambda f=frozen: f)
            result = _probe_fts5()
            assert result.ok is False, f"is_frozen()={frozen} must still fail"

    def test_does_not_use_the_frozen_only_helper_or_is_frozen(self) -> None:
        """Regression guard on the DD-11 split — same technique as
        ``TestEmbeddingProbeGating::test_does_not_use_the_frozen_only_helper``."""
        import inspect

        source = inspect.getsource(diagnostics._probe_fts5)
        assert "_vector_probe_outcome" not in source
        assert "is_frozen" not in source

    def test_line_present_in_output_by_name(self) -> None:
        """Both CI lanes grep this exact prefix — it must not drift."""
        buf = io.StringIO()
        run_doctor(out=buf)
        assert "fts5: OK" in buf.getvalue()

    def test_failure_promotes_result_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            diagnostics,
            "_probe_fts5",
            lambda: ProbeResult("fts5", False, "simulated fts5 unavailable"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "fts5: FAIL" in text
        assert "RESULT: FAIL" in text


class TestUsearchAcceleration:
    """``_usearch_acceleration`` is a detail-string helper; it must never raise."""

    def test_reports_numkong_and_simd(self) -> None:
        detail = _usearch_acceleration()
        assert "numkong=" in detail

    def test_never_raises_when_the_native_module_is_absent(self) -> None:
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(sys.modules, "usearch.compiled", None)  # type: ignore[arg-type]
            detail = _usearch_acceleration()
        assert "unavailable" in detail

    def test_numkong_no_appends_the_extensions_own_load_state(self) -> None:
        """``numkong=no`` alone cannot say WHY.

        Two causes look identical through the ``USES_NUMKONG`` flag: a
        ``_numkong`` extension that will not load here (a packaging defect —
        on Windows an unresolved dependent DLL, swallowed by usearch's bare
        ``except ImportError: pass``), and a usearch wheel simply not built
        against numkong (upstream, unfixable by packaging). The detail must
        distinguish them.
        """
        import usearch.compiled as compiled

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(compiled, "USES_NUMKONG", 0, raising=False)
            detail = _usearch_acceleration()
        assert "numkong=no" in detail
        assert "numkong ext" in detail
        assert "built without numkong" in detail

    def test_unloadable_numkong_extension_surfaces_the_real_error(self) -> None:
        """The exception text usearch swallows is the whole point of the line.

        The stub raises the exact shape Windows produces when a ``.pyd``'s
        dependent DLL cannot be resolved — the message that
        ``usearch/__init__.py``'s bare ``except ImportError: pass`` discards.
        """
        import usearch.compiled as compiled

        boom = ImportError(
            "DLL load failed while importing _numkong: The specified module could not be found."
        )
        stub = types.ModuleType("numkong")

        def _raise(name: str):
            raise boom

        stub.__getattr__ = _raise  # type: ignore[attr-defined]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(compiled, "USES_NUMKONG", 0, raising=False)
            mp.setitem(sys.modules, "numkong", stub)
            mp.delitem(sys.modules, "numkong._numkong", raising=False)
            detail = _usearch_acceleration()
        assert "numkong ext will not load" in detail
        assert "ImportError" in detail
        assert "DLL load failed while importing _numkong" in detail

    def test_extension_state_never_raises(self) -> None:
        """Helper contract: a detail string, never an exception."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(sys.modules, "numkong", None)  # type: ignore[arg-type]
            mp.delitem(sys.modules, "numkong._numkong", raising=False)
            assert isinstance(_numkong_extension_state(), str)
        assert isinstance(_numkong_extension_state(), str)


class TestEmbeddingProbeGating:
    """``embedding model`` is the only NEW gate that fails on a dev host.

    M24 F01 DD-7: the vector-store probe downgrades an unfrozen failure to a
    ``skipped`` line because native extension loading genuinely varies across
    Python builds. This one must not — model2vec is a base dependency and the
    weights are package data present in every checkout, so a host failure is a
    real defect (most usefully a missing package-data glob in a non-editable
    wheel install, which a frozen-only gate would never observe).

    These tests stub the probe deliberately: what is under test is ``run_doctor``'s
    treatment of its outcome, not the load. The real load is
    ``tests/test_doctor_embedding_model.py``.
    """

    def test_line_present_in_output_by_name(self) -> None:
        """Both CI lanes grep this exact prefix — it must not drift."""
        buf = io.StringIO()
        run_doctor(out=buf)
        assert "embedding model: OK" in buf.getvalue()

    def test_failure_is_result_fail_on_an_unfrozen_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert diagnostics.is_frozen() is False, "this test asserts the UNFROZEN behaviour"
        monkeypatch.setattr(
            diagnostics,
            "_probe_embedding_model",
            lambda: ProbeResult("embedding model", False, "simulated missing package data"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "embedding model: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_does_not_use_the_frozen_only_helper(self) -> None:
        """Regression guard on the DD-7 split.

        ``_vector_probe_outcome`` converts a failure into ``ok=True`` when
        unfrozen. If a future edit routed the embedding probe through it, the
        test above would still pass (it stubs the probe) while the real gate
        went silent on every dev host and wheel install. Assert the source of
        the probe itself never reaches for that helper.
        """
        import inspect

        source = inspect.getsource(diagnostics._probe_embedding_model)
        assert "_vector_probe_outcome" not in source


class TestEmitEncodingSafety:
    """AC-15 / build 606620: the frozen Windows doctor died mid-run.

    Both CI lanes pipe ``the-one.exe doctor``'s stdout, which Windows resolves
    to the cp1252 codec, and a probe detail containing U+2192 (the old
    embedding-probe arrow) raised ``UnicodeEncodeError`` from inside ``emit``
    and killed the process before ``RESULT:`` could print. ``run_doctor`` must
    never raise on its own output — this drives a stubbed probe with a
    non-cp1252 character through a real cp1252-encoded stream.
    """

    def test_non_cp1252_detail_does_not_crash_the_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            diagnostics,
            "_probe_fts5",
            lambda: ProbeResult("fts5", True, "arrow example → still ok"),
        )
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252")
        try:
            code = run_doctor(out=stream)
        finally:
            stream.flush()
        text = raw.getvalue().decode("cp1252")

        assert code == 0
        # The by-name substring both CI lanes grep must survive the replace.
        assert "fts5: OK" in text
        assert "RESULT: PASS" in text


class TestProbeFileWatcher:
    """Flight 4 M24 F04 L01, DD-0/DD-9, AC-6: the ``file watcher`` gate.

    Unlike every other probe in this file, ``_probe_file_watcher`` is
    stubbed by an autouse fixture (``_stub_file_watcher_probe`` above, the
    ``_stub_embedding_probe`` precedent) — its round-trip half costs real
    wall-clock time. These tests call the module-top-imported
    ``_probe_file_watcher`` directly, which the stub (a
    ``monkeypatch.setattr(diagnostics, …)`` rebind of the module attribute)
    does not affect, per DD-9 and the ``_probe_usearch`` precedent.
    """

    def test_real_round_trip_on_tmp_path(self, tmp_path) -> None:
        """The real round-trip through the real ``watchfiles.watch`` (AC-6's
        "one AC through the real ``watch``" rule — the factory-seam
        equivalent the watcher module uses would pass green against a
        library that swallowed the error, which this test does not use).

        Skips when a short self-probe shows this host/filesystem does not
        deliver native change events at all (a drvfs-mounted ``TMPDIR``, a
        container without inotify) — there ``_probe_file_watcher`` itself
        legitimately reads ``skipped —`` (Edge Cases), which is not what
        this test is built to assert.
        """
        import watchfiles

        gen = watchfiles.watch(
            str(tmp_path),
            watch_filter=None,
            debounce=50,
            step=25,
            rust_timeout=200,
            yield_on_timeout=True,
            force_polling=False,
            ignore_permission_denied=False,
            raise_interrupt=False,
            debug=False,
            poll_delay_ms=300,
            recursive=True,
        )
        delivered = False
        n = 0
        try:
            start = time.monotonic()
            for changes in gen:
                if changes:
                    delivered = True
                    break
                if time.monotonic() - start > 1.0:
                    break
                n += 1
                (tmp_path / f"self-probe-{n}.txt").write_text("x")
        finally:
            gen.close()

        if not delivered:
            pytest.skip(
                "this host/filesystem does not deliver native change "
                "notification events within the self-probe deadline"
            )

        result = _probe_file_watcher()
        assert result.ok is True
        assert result.detail == "native change notification round-trip OK"

    def test_import_failure_is_ok_false_when_unfrozen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(diagnostics, "is_frozen", lambda: False)

        def _boom():
            raise ImportError("simulated missing watchfiles")

        monkeypatch.setattr(diagnostics, "_import_watchfiles", _boom)
        result = _probe_file_watcher()
        assert result.ok is False
        assert "watchfiles import failed" in result.detail

    def test_import_failure_is_ok_false_when_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(diagnostics, "is_frozen", lambda: True)

        def _boom():
            raise ImportError("simulated missing watchfiles")

        monkeypatch.setattr(diagnostics, "_import_watchfiles", _boom)
        result = _probe_file_watcher()
        assert result.ok is False
        assert "watchfiles import failed" in result.detail

    def test_round_trip_failure_unfrozen_is_informational_skip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(diagnostics, "is_frozen", lambda: False)

        class _BoomWatchfiles:
            @staticmethod
            def watch(*args, **kwargs):
                raise RuntimeError("simulated watch failure")

        monkeypatch.setattr(diagnostics, "_import_watchfiles", lambda: _BoomWatchfiles())
        result = _probe_file_watcher()
        assert result.ok is True
        assert result.detail.startswith("skipped — ")
        assert "import OK; round-trip:" in result.detail

    def test_round_trip_failure_frozen_is_hard_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(diagnostics, "is_frozen", lambda: True)

        class _BoomWatchfiles:
            @staticmethod
            def watch(*args, **kwargs):
                raise RuntimeError("simulated watch failure")

        monkeypatch.setattr(diagnostics, "_import_watchfiles", lambda: _BoomWatchfiles())
        result = _probe_file_watcher()
        assert result.ok is False
        assert "import OK; round-trip:" in result.detail

    def test_gates_list_has_twelve_names_ending_with_mcp_sdk(self) -> None:
        """The full gate line-up, in order, both CI lanes' needle depends on
        being present and last."""
        buf = io.StringIO()
        run_doctor(out=buf)
        text = buf.getvalue()
        gate_names = re.findall(r"(?m)^  ([^:]+): (?:OK|FAIL)", text)
        assert gate_names == [
            "child spawn",
            "python interpreter",
            "desktop shell",
            "llm providers",
            "model catalog",
            "usearch",
            "fts5",
            "embedding model",
            "file watcher",
            "window chrome",
            "time zones",
            "mcp sdk",
        ]

    def test_mcp_sdk_probe_passes_with_version_detail(self) -> None:
        from the_one.diagnostics import _probe_mcp_sdk

        result = _probe_mcp_sdk()
        assert result.name == "mcp sdk"
        assert result.ok is True, result.detail
        assert "httpcore2" in result.detail
        assert re.fullmatch(
            r"mcp \d+\.\d+\.\d+\S*, handshake \d{4}-\d{2}-\d{2}, "
            r"modern \d{4}-\d{2}-\d{2}, httpcore2 \S+",
            result.detail,
        )

    def test_mcp_sdk_probe_missing_httpcore2_fails_with_reason(self, monkeypatch) -> None:
        import importlib.metadata

        from the_one.diagnostics import _probe_mcp_sdk

        real = importlib.metadata.version

        def _version(name):
            if name == "httpcore2":
                raise importlib.metadata.PackageNotFoundError(name)
            return real(name)

        monkeypatch.setattr(importlib.metadata, "version", _version)
        result = _probe_mcp_sdk()
        assert result.ok is False
        assert "httpcore2" in result.detail

    def test_mcp_sdk_probe_failure_carries_reason(self, monkeypatch) -> None:
        from the_one import diagnostics
        from the_one.diagnostics import _probe_mcp_sdk

        def _boom():
            raise ImportError("simulated missing httpx2")

        monkeypatch.setattr(diagnostics, "_import_mcp_sdk", _boom)
        result = _probe_mcp_sdk()
        assert result.ok is False
        assert "simulated missing httpx2" in result.detail
        assert result.detail.isascii()

    def test_source_names_every_dd0_knob(self) -> None:
        """Source-level guard (the ``_probe_usearch``/embedding-probe
        precedent's discipline, applied to DD-0): every ``watchfiles.watch``
        knob DD-0 requires pinned explicitly must appear, by name, in the
        probe's source — a future edit that drops one silently
        reintroduces an inherited library or environment default."""
        import inspect

        # The module-top-imported name, not `diagnostics._probe_file_watcher`
        # — the autouse stub above rebinds the module attribute, but this
        # name was captured at import time and is unaffected (the same
        # mechanism that lets the round-trip tests above bypass the stub).
        source = inspect.getsource(_probe_file_watcher)
        for knob in (
            "force_polling",
            "raise_interrupt",
            "debug",
            "poll_delay_ms",
            "recursive",
            "debounce",
            "step",
            "rust_timeout",
            "yield_on_timeout",
            "ignore_permission_denied",
        ):
            assert knob in source, f"missing DD-0 knob {knob!r} from _probe_file_watcher source"

    def test_line_present_in_output_by_name(self) -> None:
        """Both CI lanes grep this exact prefix — it must not drift. Uses
        the autouse-stubbed probe, same as the other by-name presence
        tests in this file."""
        buf = io.StringIO()
        run_doctor(out=buf)
        assert "file watcher: OK" in buf.getvalue()


class TestWindowChromeProbe:
    def _fake_windows(self, monkeypatch, build, hr=0x80070057, missing=False):
        import ctypes
        import types

        from the_one import diagnostics
        from the_one.interfaces.desktop import chrome

        monkeypatch.setattr(diagnostics.sys, "platform", "win32")
        monkeypatch.setattr(chrome, "windows_build", lambda: build)
        if missing:

            class _NoDwm:
                @property
                def dwmapi(self):
                    raise OSError("dwmapi.dll not found")

            windll = _NoDwm()
        else:
            windll = types.SimpleNamespace(
                dwmapi=types.SimpleNamespace(DwmSetWindowAttribute=lambda *a: hr)
            )
        monkeypatch.setattr(ctypes, "windll", windll, raising=False)

    def test_off_windows_is_skipped(self, monkeypatch) -> None:
        from the_one import diagnostics

        monkeypatch.setattr(diagnostics.sys, "platform", "linux")
        r = diagnostics._probe_window_chrome()
        assert (r.name, r.ok, r.detail) == ("window chrome", True, "skipped (not Windows)")

    def test_caption_colours_supported(self, monkeypatch) -> None:
        from the_one import diagnostics

        self._fake_windows(monkeypatch, 26100)
        r = diagnostics._probe_window_chrome()
        assert r.ok is True
        assert r.detail == "caption colours supported (build 26100, probe 0x80070057)"

    def test_dark_mode_only_below_22000(self, monkeypatch) -> None:
        from the_one import diagnostics

        self._fake_windows(monkeypatch, 20348)
        r = diagnostics._probe_window_chrome()
        assert r.ok is True
        assert r.detail.startswith("dark mode only (build 20348, probe 0x")

    def test_dwmapi_missing_fails_without_raising(self, monkeypatch) -> None:
        from the_one import diagnostics

        self._fake_windows(monkeypatch, 26100, missing=True)
        r = diagnostics._probe_window_chrome()
        assert r.ok is False
        assert "dwmapi" in r.detail

    def test_detail_is_ascii(self, monkeypatch) -> None:
        from the_one import diagnostics

        for build in (26100, 20348):
            self._fake_windows(monkeypatch, build)
            assert diagnostics._probe_window_chrome().detail.isascii()
        self._fake_windows(monkeypatch, 1, missing=True)
        assert diagnostics._probe_window_chrome().detail.isascii()


class TestTimeZonesProbe:
    """M28 F1 L1 (DD9): the unconditional `time zones` gate."""

    def test_ok_and_ascii(self) -> None:
        r = diagnostics._probe_time_zones()
        assert (r.name, r.ok) == ("time zones", True)
        assert r.detail.isascii()
        assert "zones (tzdata " in r.detail and "system zone: " in r.detail

    def test_short_zone_list_fails(self, monkeypatch) -> None:
        from the_one import time_zones

        monkeypatch.setattr(time_zones, "canonical_zones", lambda: ["UTC"])
        r = diagnostics._probe_time_zones()
        assert r.ok is False and "only 1 zones" in r.detail

    def test_never_raises(self, monkeypatch) -> None:
        from the_one import time_zones

        def boom():
            raise RuntimeError("zone data gone")

        monkeypatch.setattr(time_zones, "canonical_zones", boom)
        r = diagnostics._probe_time_zones()
        assert r.ok is False and "RuntimeError" in r.detail

    def test_detection_failure_does_not_affect_ok(self, monkeypatch) -> None:
        from the_one import time_zones

        monkeypatch.setattr(time_zones, "detect_system_zone", lambda: None)
        r = diagnostics._probe_time_zones()
        assert r.ok is True and "none detected" in r.detail

    def test_line_present_in_output_by_name(self) -> None:
        buf = io.StringIO()
        run_doctor(out=buf)
        assert "time zones: OK" in buf.getvalue()


# ── M32 F2 L02: Linux frozen desktop-shell split (AC4) and advisory lines (AC5) ─


class TestFrozenLinuxDesktopShell:
    @pytest.fixture(autouse=True)
    def _frozen_linux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from the_one.interfaces.desktop import host

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(diagnostics, "is_frozen", lambda: True)
        monkeypatch.setattr(host, "host_has_desktop_gtk", lambda: True)
        monkeypatch.setattr(host, "display_session", lambda: "x11")
        monkeypatch.setattr(diagnostics, "bundle_has_modules", lambda names: [])
        # An import of pystray raises ValueError (as with no Gtk typelib):
        # a test that reaches it fails loudly, so "never imported" is proven.
        import importlib.abc

        class _Bomb(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name == "pystray" or name.startswith("pystray."):
                    raise ValueError("Namespace Gtk not available")
                return None

        monkeypatch.delitem(sys.modules, "pystray", raising=False)
        monkeypatch.setattr(sys, "meta_path", [_Bomb(), *sys.meta_path])
        monkeypatch.setitem(sys.modules, "PIL", _make_stub_module("PIL"))

    def test_no_gtk_ok_browser_wording_no_pystray(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from the_one.interfaces.desktop import host

        monkeypatch.setattr(host, "host_has_desktop_gtk", lambda: False)
        r = _probe_desktop_shell()
        assert r.ok and "opens in the browser" in r.detail
        assert "skipped" not in r.detail

    def test_no_gtk_pystray_missing_from_bundle_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from the_one.interfaces.desktop import host

        monkeypatch.setattr(host, "host_has_desktop_gtk", lambda: False)
        monkeypatch.setattr(diagnostics, "bundle_has_modules", lambda names: ["pystray"])
        r = _probe_desktop_shell()
        assert not r.ok and "pystray" in r.detail

    def test_no_display_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from the_one.interfaces.desktop import host

        monkeypatch.setattr(host, "display_session", lambda: None)
        asked: list = []
        monkeypatch.setattr(
            diagnostics, "bundle_has_modules", lambda names: asked.append(tuple(names)) or []
        )
        r = _probe_desktop_shell()
        assert r.ok and "no display session" in r.detail and "skipped" not in r.detail
        assert ("pystray", "gi", "webview.platforms.gtk") in asked

    def test_no_display_missing_module_fails_naming_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from the_one.interfaces.desktop import host

        monkeypatch.setattr(host, "display_session", lambda: None)
        monkeypatch.setattr(diagnostics, "bundle_has_modules", lambda names: ["gi"])
        r = _probe_desktop_shell()
        assert not r.ok and "gi" in r.detail

    def test_no_backend_ok_without_pystray(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from the_one.interfaces.desktop import host

        monkeypatch.setattr(host, "choose_pystray_backend", lambda: None)
        r = _probe_desktop_shell()
        assert r.ok and "no tray backend" in r.detail and "skipped" not in r.detail

    @pytest.mark.parametrize("before", [None, "dummy"])
    def test_backend_import_sets_and_restores_env(
        self, monkeypatch: pytest.MonkeyPatch, before: str | None
    ) -> None:
        import os

        from the_one.interfaces.desktop import host

        monkeypatch.setattr(host, "choose_pystray_backend", lambda: "gtk")
        if before is None:
            monkeypatch.delenv("PYSTRAY_BACKEND", raising=False)
        else:
            monkeypatch.setenv("PYSTRAY_BACKEND", before)
        import builtins

        seen = {"during": None}
        monkeypatch.setitem(sys.modules, "pystray", types.ModuleType("pystray"))
        orig = os.environ.get("PYSTRAY_BACKEND")
        real_import = builtins.__import__

        def spy(name, *a, **k):
            if name == "pystray":
                seen["during"] = os.environ.get("PYSTRAY_BACKEND")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", spy)
        r = _probe_desktop_shell()
        monkeypatch.setattr(builtins, "__import__", real_import)
        assert r.ok and "pystray (gtk)" in r.detail
        assert seen["during"] == "gtk"
        assert os.environ.get("PYSTRAY_BACKEND") == orig

    def test_backend_import_failure_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from the_one.interfaces.desktop import host

        monkeypatch.setattr(host, "choose_pystray_backend", lambda: "appindicator")
        r = _probe_desktop_shell()  # the bomb finder raises ValueError on import
        assert not r.ok


def test_win32_desktop_shell_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "pystray", _make_stub_module("pystray"))
    monkeypatch.setitem(sys.modules, "PIL", _make_stub_module("PIL"))
    r = _probe_desktop_shell()
    assert (r.ok, r.detail) == (True, "pystray + PIL importable")


def test_bundle_has_modules_does_not_import_package_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """pystray.__init__ would run backend(); the check must not import it."""
    monkeypatch.delitem(sys.modules, "pystray", raising=False)
    monkeypatch.delitem(sys.modules, "pystray._base", raising=False)
    import importlib.util

    if importlib.util.find_spec("pystray") is None:
        pytest.skip("pystray not installed")
    assert diagnostics.bundle_has_modules(("pystray", "pystray._base")) == []
    assert "pystray" not in sys.modules
    assert diagnostics.bundle_has_modules(("pystray._nope", "no_such_pkg_xyz")) == [
        "pystray._nope",
        "no_such_pkg_xyz",
    ]


class TestAdvisoryLines:
    @pytest.mark.parametrize(
        "selection,needle",
        [
            (("passthrough", "test bypass"), "test bypass"),
            (("passthrough", "non-Linux host (darwin)"), "non-Linux"),
            (("passthrough", "bubblewrap not installed"), "not installed"),
            (("passthrough", "user namespaces unavailable"), "user namespaces"),
            (("passthrough", "user namespace probe failed"), "probe failed"),
            (("bubblewrap", ""), "sandbox: bubblewrap"),
        ],
    )
    def test_sandbox_line(self, monkeypatch: pytest.MonkeyPatch, selection, needle) -> None:
        from the_one.platform.sandbox import factory

        monkeypatch.setattr(factory, "describe_selection", lambda: selection)
        buf = io.StringIO()
        code = run_doctor(out=buf)
        out = buf.getvalue()
        line = next(ln for ln in out.splitlines() if ln.strip().startswith("sandbox:"))
        assert needle in line
        assert code == 0
        assert out.index("mcp sdk:") < out.index("sandbox:") < out.index("RESULT:")
        line.encode("cp1252")
        next(ln for ln in out.splitlines() if ln.strip().startswith("tray:")).encode("cp1252")

    def test_tray_lines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from the_one.interfaces.desktop import host

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(host, "host_has_desktop_gtk", lambda: False)
        assert diagnostics._tray_line() == "tray: none — no desktop GTK on this host"
        monkeypatch.setattr(host, "host_has_desktop_gtk", lambda: True)
        monkeypatch.setattr(host, "display_session", lambda: None)
        assert diagnostics._tray_line() == "tray: none — no display session"
        monkeypatch.setattr(host, "display_session", lambda: "x11")
        monkeypatch.setattr(host, "choose_pystray_backend", lambda: "gtk")
        monkeypatch.setattr(host, "detect_tray", lambda b: ("xembed", "X11 system tray present"))
        assert diagnostics._tray_line() == "tray: xembed — X11 system tray present"
        monkeypatch.setattr(sys, "platform", "win32")
        assert diagnostics._tray_line() == "tray: system tray (Windows)"
        monkeypatch.setattr(sys, "platform", "darwin")
        assert diagnostics._tray_line() == "tray: dock — macOS keeps the app in the Dock"


class TestMacosDoctor:
    """M32 F3 L5: darwin desktop-shell gate, ``path:`` line, stub-aware runtimes."""

    def _freeze(self, monkeypatch: pytest.MonkeyPatch, frozen: bool = True) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        if frozen:
            monkeypatch.setattr(sys, "frozen", True, raising=False)
            monkeypatch.setattr(sys, "_MEIPASS", "/bundle", raising=False)
        else:
            monkeypatch.delattr(sys, "frozen", raising=False)
            monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    def test_cocoa_present_is_ok_without_the_word_skipped(self, monkeypatch) -> None:
        self._freeze(monkeypatch)
        seen: list[tuple[str, ...]] = []
        monkeypatch.setattr(
            diagnostics, "bundle_has_modules", lambda names: seen.append(tuple(names)) or []
        )
        r = _probe_desktop_shell()
        assert (r.ok, r.detail) == (True, "Cocoa backend present")
        assert "skipped" not in r.detail
        assert seen == [("webview.platforms.cocoa", "objc", "AppKit", "WebKit")]

    def test_frozen_missing_fails(self, monkeypatch) -> None:
        self._freeze(monkeypatch)
        monkeypatch.setattr(diagnostics, "bundle_has_modules", lambda names: ["objc", "AppKit"])
        r = _probe_desktop_shell()
        assert not r.ok
        assert r.detail == "missing from the bundle: objc, AppKit"

    def test_not_frozen_missing_is_skipped_but_ok(self, monkeypatch) -> None:
        self._freeze(monkeypatch, frozen=False)
        monkeypatch.setattr(diagnostics, "bundle_has_modules", lambda names: ["objc"])
        r = _probe_desktop_shell()
        assert r.ok and "skipped" in r.detail

    def test_never_imports_cocoa_or_pystray(self, monkeypatch) -> None:
        self._freeze(monkeypatch)
        monkeypatch.setattr(diagnostics, "bundle_has_modules", lambda names: [])
        for mod in ("webview.platforms.cocoa", "AppKit", "pystray"):
            monkeypatch.delitem(sys.modules, mod, raising=False)
        _probe_desktop_shell()
        assert not {"webview.platforms.cocoa", "AppKit", "pystray"} & set(sys.modules)

    def test_path_line_only_on_frozen_darwin(self, monkeypatch) -> None:
        from the_one.platform import env as env_mod

        self._freeze(monkeypatch)
        monkeypatch.setattr(env_mod, "_PRIMED", ("login shell", "", ("/a",)))
        assert "path: login shell" in diagnostics._advisory_lines()
        monkeypatch.setattr(env_mod, "_PRIMED", ("static fallback", "zsh exited 1", ()))
        assert "path: static fallback — zsh exited 1" in diagnostics._advisory_lines()
        monkeypatch.setattr(sys, "platform", "linux")
        assert not any(ln.startswith("path:") for ln in diagnostics._advisory_lines())
        self._freeze(monkeypatch, frozen=False)
        assert not any(ln.startswith("path:") for ln in diagnostics._advisory_lines())

    def test_detect_runtimes_reports_the_stub_as_not_found(self, monkeypatch) -> None:
        from the_one.platform import interpreter as interp_mod

        self._freeze(monkeypatch)
        monkeypatch.setattr(interp_mod, "_command_line_tools_installed", lambda: False)

        def which(name, path=None):
            return f"{path}/{name}" if path == "/usr/bin" else None

        monkeypatch.setattr(interp_mod.shutil, "which", which)  # the same module object
        by_name = {r.name: r for r in detect_runtimes({"PATH": "/usr/bin"})}
        for name in ("python", "python3"):
            assert by_name[name].ok
            assert by_name[name].detail == (
                "not found — only the macOS Command Line Tools stub is on PATH; "
                "install Python 3 (python.org or Homebrew)"
            )
        assert by_name["node"].detail == "found at /usr/bin/node"

    def test_detect_runtimes_walks_past_the_stub(self, monkeypatch) -> None:
        from the_one.platform import interpreter as interp_mod

        self._freeze(monkeypatch)
        monkeypatch.setattr(interp_mod, "_command_line_tools_installed", lambda: False)
        table = {("python3", "/usr/bin"): "/usr/bin/python3", ("python3", "/opt"): "/opt/python3"}
        monkeypatch.setattr(interp_mod.shutil, "which", lambda c, path=None: table.get((c, path)))
        by_name = {r.name: r for r in detect_runtimes({"PATH": "/usr/bin:/opt"})}
        assert by_name["python3"].detail == "found at /opt/python3"


pytestmark = pytest.mark.usefixtures("stub_desktop_host")
