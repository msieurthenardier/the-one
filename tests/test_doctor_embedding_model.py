"""Real-load tests for the ``embedding model`` doctor probe (M24 F01 L02).

**This file exists because of an autouse fixture.** ``tests/test_doctor.py``
patches ``_probe_embedding_model`` for every test in that module, so the 16
``run_doctor(`` call sites there do not each pay the 62 MiB model load. pytest
offers no opt-out from an autouse fixture — the usual marker workaround needs
``request.node`` to be the test function, and at module scope it is the Module —
so the dedicated real-load coverage lives in a separate file instead.

Per M24 F01 DD-7 this is the **only host-side proof that the real asset loads**.
It must never be mocked or skipped. Two of the three tests below do stub
``StaticModel``/the model path, but only to observe the probe's *guards*; the
first one loads the committed weights for real.

Note the asset is untracked until a human stages it (the leg's terminal
handoff), so on a machine that has not run ``make refresh-embedding-model``
these tests fail — which is the correct signal, not a reason to skip.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from the_one import diagnostics
from the_one.diagnostics import _EMBEDDING_DIM, _probe_embedding_model


def _packaged_model_dir() -> Path:
    """The directory the probe resolves, computed the same way the probe does."""
    from importlib.resources import files

    return Path(
        str(
            files(diagnostics._EMBEDDING_PACKAGE).joinpath(
                "data", diagnostics._EMBEDDING_MODEL_DIRNAME
            )
        )
    )


class TestRealLoad:
    def test_probe_loads_the_committed_weights(self) -> None:
        """Load the real bundled model and assert on the EMITTED DETAIL.

        Leg 1's lesson: a naive monkeypatch that the probe's broad ``except``
        swallows yields a test that passes while asserting nothing. So this
        checks the concrete resolved values the probe reports — width, norm,
        weights size, RSS, resolved path — not merely ``ok``.
        """
        result = _probe_embedding_model()
        assert result.ok is True, result.detail
        assert result.name == "embedding model"
        assert f"{_EMBEDDING_DIM}-dim" in result.detail
        # DD-1's dtype, read off the returned array by the probe itself.
        assert "float16 vector" in result.detail
        assert "norm " in result.detail
        # The truncated-file / LFS-pointer tell: the byte size is in the line.
        assert "model.safetensors=" in result.detail
        # DD-4 read path — Flight 2 needs this figure for the float16-vs-int8
        # vector-storage decision, and no CI task measures memory.
        assert "peak RSS" in result.detail
        assert diagnostics._EMBEDDING_MODEL_DIRNAME in result.detail

    def test_reported_weights_size_matches_the_file_on_disk(self) -> None:
        """The size in the detail line is read, not hardcoded."""
        weights = _packaged_model_dir() / diagnostics._EMBEDDING_WEIGHTS_FILENAME
        result = _probe_embedding_model()
        assert f"model.safetensors={weights.stat().st_size:,} bytes" in result.detail

    def test_weights_clear_the_github_blob_limit(self) -> None:
        """DD-2's whole basis: float16 keeps the single blob under 100 MiB.

        Asserted here as well as in the generator because this is the check that
        cannot be performed after the fact — once the blob is pushed it is in
        history permanently.
        """
        weights = _packaged_model_dir() / diagnostics._EMBEDDING_WEIGHTS_FILENAME
        assert weights.stat().st_size < 100 * 1024 * 1024


class TestOfflineInvariant:
    """DD-5: the probe must be INCAPABLE of passing by download.

    ``model2vec._resolve_folder`` returns a local directory only if it exists
    and otherwise falls through to ``snapshot_download()``. On a networked
    machine a model tree-shaken out of the bundle would then produce a *passing*
    probe that fetched the weights over the network — the same fail-open the
    model-catalog probe was written against, one layer out.
    """

    def test_missing_packaged_directory_fails_rather_than_downloading(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Point the probe at a directory that genuinely is not there.

        Deliberately NOT implemented by renaming the real directory on disk: the
        asset is 62 MiB and untracked until a human stages it, so a test that
        moves it could leave the working tree needing a re-download. Repointing
        the name produces the identical filesystem miss with nothing at stake.

        Also guards against the wrong assertion: with an ABSOLUTE path — which
        is what ``importlib.resources.files(...)`` yields — a missed load raises
        ``HFValidationError`` from ``validate_repo_id``, not the
        ``LocalEntryNotFoundError`` a relative or repo-id-shaped string gives.
        Pinning either would be pinning the wrong thing. What matters is that
        ``from_pretrained`` is never reached at all.
        """
        sentinel = "definitely-not-a-real-model-directory"
        monkeypatch.setattr(diagnostics, "_EMBEDDING_MODEL_DIRNAME", sentinel)

        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("from_pretrained must not be reached — this is the DD-5 breach")

        import model2vec

        monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", _explode)

        result = _probe_embedding_model()
        assert result.ok is False
        assert "packaged model directory not found" in result.detail
        assert sentinel in result.detail

    def test_hf_hub_offline_is_set_before_the_load(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The env var does the real work; the path check is defence in depth.

        Captures ``HF_HUB_OFFLINE`` at the moment ``from_pretrained`` is called,
        so this fails if a future edit sets it after the load or drops it.
        """
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        seen: dict[str, str | None] = {}

        class _StubModel:
            @staticmethod
            def encode(text: str) -> list[float]:
                return [0.5] * _EMBEDDING_DIM

        def _capture(path: str, *args: object, **kwargs: object) -> _StubModel:
            seen["offline"] = os.environ.get("HF_HUB_OFFLINE")
            seen["path"] = path
            return _StubModel()

        import model2vec

        monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", _capture)

        result = _probe_embedding_model()
        # Assert on the emitted detail too, not just ok — a stub the probe's
        # broad `except` swallowed would leave `seen` empty and `ok` False.
        assert result.ok is True, result.detail
        assert f"{_EMBEDDING_DIM}-dim" in result.detail
        assert seen["offline"] == "1"
        # It loaded from the packaged path, not from a repo id.
        assert str(seen["path"]).endswith(diagnostics._EMBEDDING_MODEL_DIRNAME)
        assert os.path.isabs(str(seen["path"]))

    def test_huggingface_hub_constant_is_forced_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``HF_HUB_OFFLINE`` is bound ONCE, at huggingface_hub import time.

        Setting the environment variable after the package is already imported
        is too late for ``huggingface_hub.constants.HF_HUB_OFFLINE``, which is
        the value the hub code actually consults. ``_force_hf_offline`` sets
        both; this covers the second.
        """
        import huggingface_hub.constants as hf_constants

        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        monkeypatch.setattr(hf_constants, "HF_HUB_OFFLINE", False, raising=False)

        diagnostics._force_hf_offline()

        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert hf_constants.HF_HUB_OFFLINE is True


class TestPeakRss:
    def test_reports_a_plausible_positive_figure(self) -> None:
        """Advisory, but it must be a real number on the host that measures it."""
        peak, reason = diagnostics._peak_rss_bytes()
        assert peak is not None, reason
        assert reason is None
        # A Python process that has imported numpy and tokenizers is comfortably
        # over 8 MiB; anything under that means the units are wrong.
        assert peak > 8 * 1024 * 1024


class _FakeWinFunc:
    """A stand-in for a ctypes ``_FuncPtr`` that records restype/argtypes.

    Unlike a real Windows DLL function, this does not perform ctypes' own
    argument marshalling — but it is enough to prove the production code
    *declares* ``restype``/``argtypes`` before calling, which is what fixes
    the real truncated-HANDLE bug (verified on windows-worker; see the flight
    log). ``return_value`` may be a plain value or a callable of
    ``(*args) -> value`` for cases that need to inspect/mutate arguments.
    """

    def __init__(self, return_value):
        self._return_value = return_value
        self.restype = None
        self.argtypes = None
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)
        if callable(self._return_value):
            return self._return_value(*args)
        return self._return_value


class TestPeakRssWindowsBranch:
    """Exercises the ``os.name == "nt"`` branch from a Linux host.

    ``ctypes.wintypes`` imports fine on Linux, but ``ctypes.WinDLL`` does not
    exist there, so it is patched onto the module for the duration of each
    test. ``ctypes.get_last_error`` is Windows-only for the same reason.

    The counters struct built here mirrors ``_ProcessMemoryCounters`` inside
    ``_peak_rss_bytes`` field-for-field (same field names, order and ctypes
    types), so a pointer cast against it lands on the identical in-memory
    layout the production structure produces in this same process — no
    reliance on the private class or on hardcoded byte offsets.
    """

    def _fake_counters_type(self):
        import ctypes
        from ctypes import wintypes

        class _FakeProcessMemoryCounters(ctypes.Structure):
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

        return _FakeProcessMemoryCounters

    def test_success_declares_handle_semantics_and_returns_bytes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ctypes
        from ctypes import wintypes

        monkeypatch.setattr(os, "name", "nt")
        fake_counters_type = self._fake_counters_type()

        expected_peak = 25_288_704  # observed on windows-worker with the fix
        get_current_process = _FakeWinFunc(return_value=-1)

        def fill_counters(handle, counters_ref, cb):
            # Prove HANDLE semantics were declared before this call: on real
            # Windows, an undeclared restype truncates the -1 pseudo-handle to
            # 32 bits before it ever reaches here — the exact bug this fixes.
            assert get_current_process.restype is wintypes.HANDLE
            assert memory_info.argtypes is not None
            assert memory_info.argtypes[0] is wintypes.HANDLE
            assert handle == -1
            counters = ctypes.cast(counters_ref, ctypes.POINTER(fake_counters_type)).contents
            counters.PeakWorkingSetSize = expected_peak
            return 1

        memory_info = _FakeWinFunc(return_value=fill_counters)

        class _FakeKernel32:
            GetCurrentProcess = get_current_process
            K32GetProcessMemoryInfo = memory_info

        def fake_win_dll(name, use_last_error=False):
            assert name == "kernel32"
            return _FakeKernel32()

        monkeypatch.setattr(ctypes, "WinDLL", fake_win_dll, raising=False)
        monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)

        peak, reason = diagnostics._peak_rss_bytes()

        assert reason is None
        assert peak == expected_peak

    def test_failure_reports_get_last_error_in_reason(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ctypes

        monkeypatch.setattr(os, "name", "nt")

        get_current_process = _FakeWinFunc(return_value=-1)
        memory_info = _FakeWinFunc(return_value=0)  # failure: returns FALSE

        class _FakeKernel32:
            GetCurrentProcess = get_current_process
            K32GetProcessMemoryInfo = memory_info

        def fake_win_dll(name, use_last_error=False):
            return _FakeKernel32()

        monkeypatch.setattr(ctypes, "WinDLL", fake_win_dll, raising=False)
        monkeypatch.setattr(ctypes, "get_last_error", lambda: 6, raising=False)

        peak, reason = diagnostics._peak_rss_bytes()

        assert peak is None
        assert reason is not None
        assert "GetLastError" in reason
        assert "6" in reason
