"""Tests for ``the-one doctor`` (M15 F5, DD5) — ``the_one.diagnostics``.

The doctor must (a) spawn a probe child through the real spawn env, (b) detect
runtimes, (c) print a structured PASS/FAIL with a ``child spawn: OK``/``FAIL``
line, and (d) exit non-zero on failure. Runs LLM-free. These tests exercise the
host (non-frozen) path — the dev-loop / CI-host case the leg explicitly requires
to pass before a frozen binary exists — plus simulated-failure paths.
"""

from __future__ import annotations

import io
import sqlite3
import sys
import types

import pytest

from the_one import diagnostics
from the_one.diagnostics import (
    ProbeResult,
    _numkong_extension_state,
    _probe_desktop_shell,
    _probe_fts5,
    _probe_llm_providers,
    _probe_model_catalog,
    _probe_usearch,
    _usearch_acceleration,
    detect_runtimes,
    run_doctor,
)


# The `embedding model` gate is UNCONDITIONAL (M24 F01 DD-7), so without this
# every ``run_doctor(`` call in this file — there are 19, across 9 classes —
# would load the 62 MiB bundled potion-retrieval-32M weights. Patching a single
# "host test" would leave eighteen still paying for it.
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
