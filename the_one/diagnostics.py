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
import subprocess
import sys
from dataclasses import dataclass

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


def run_doctor(out=None) -> int:
    """Run all diagnostics, print a structured report, return an exit code.

    Returns 0 when the load-bearing probes pass (child spawn + interpreter),
    non-zero otherwise. Runtime detection lines are advisory and never by
    themselves fail the run. ``out`` defaults to ``sys.stdout``; tests pass a
    buffer.
    """
    stream = out if out is not None else sys.stdout

    def emit(line: str) -> None:
        print(line, file=stream)

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
    gates = [spawn, interp, desktop, llm_providers, model_catalog]

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
