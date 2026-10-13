#!/usr/bin/env python3
"""Windows test-copy helper (Mission 25 Flight 5, DD10).

Run from WSL: ``.venv/bin/python scripts/windows_test_copy.py <command> ...``.

It builds, freezes, launches, observes and stops a *test copy* of the working
tree on the operator's real Windows desktop, with the refusals the flight's DD10
lists (ports, data directories, ``.env``, process identity, hands-off, a snapshot
of the operator's installation). Leg 1a is the non-injecting half; leg 1b adds the
gated input (``keys``, ``click``, ``drag``, ``show-window``), captures (``capture``,
``pixel``), the helper's own windows (``own-window``), ``front`` and
``focus-save``/``focus-restore``. Nothing is ever sent to a window that is not the gate
tree's or one of the helper's own, and every gesture waits for the operator to be idle.
It paints nothing (no DWM colours: those are throwaway spike scripts).

Shape: one file, two halves.

* The WSL-side CLI (``main``) parses arguments, validates, copies files through
  ``/mnt/c`` and calls the Windows half.
* The Windows half is this file's own source, piped on stdin to
  ``C:\\Python311\\python.exe -`` with a one-line prefix that carries the JSON
  request (``_WIN_REQUEST``). It uses the standard library only (``ctypes``,
  ``winreg``, ``subprocess``), so it works before any venv exists, and nothing is
  ever installed into ``C:\\Python311``.

Everything above ``# --- Windows half`` is pure (no Windows calls) and is covered
by ``tests/test_windows_test_copy.py`` on Linux. Every ``ctypes.windll`` / ``winreg``
use is lazy, so the module imports on Linux.

Exit codes: 0 ok, 2 a refusal (the message names the rule), 3 the hands-off wait
timed out, 4 a failed snapshot comparison, 5 a gesture aborted mid-way (everything
released), 6 the session looks locked.
"""

import argparse
import base64
import ctypes
import hashlib
import json
import ntpath
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent if "__file__" in globals() else Path(".")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PYTHON_WIN = "/mnt/c/Python311/python.exe"
BASE_PYTHON_DIR = "C:\\Python311"
SENTINEL = ".the-one-f5-root"
ROOT_LEAF_PREFIX = "the-one-f5"
RESULT_MARK = "@@RESULT@@"
MAIN_WINDOW_TITLE = "GleepGlorp AI"
SPLASH_WINDOW_TITLE = "GleepGlorp AI \u2014 starting"

FORBIDDEN_PORTS = {
    8484: "the operator's installed the-one-app.exe (production instance)",
    8485: "the Flight Director's preview instance",
}
MIN_APP_PORT = 8490
MIN_CDP_PORT = 9390
INSTALLED_PORT = 8484

HANDS_OFF_WINDOW_MS = 5000
HANDS_OFF_WAIT_S = 60
TICK_MASK = 0xFFFFFFFF

OPERATOR_FILES = ("api-credential", ".env", "window-chrome.json", "window-state.json")
ENV_PREFIXES = ("WEBVIEW2_", "THE_ONE_")
# Names the sync never deletes (build products and the editable install).
SYNC_PROTECTED_PARTS = ("dist", "build", "__pycache__")
SYNC_PROTECTED_SUFFIXES = (".egg-info",)
# The dependency-closure commands, pinned to ci/tasks/windows-installer-build.yml
# by tests/test_windows_test_copy.py (squawk 0124). Argument tails after
# ``python -m uv export`` / ``python -m pip install``.
CLOSURE_UV_EXPORT_ARGS = (
    "--no-dev", "--no-emit-project", "--extra", "gui", "--extra", "all-llms",
    "--format", "requirements-txt",
)  # fmt: skip
CLOSURE_PIP_REQUIREMENTS_ARGS = ("-r", "{requirements}", "--no-deps", "--quiet")
CLOSURE_PIP_EDITABLE_ARGS = ("-e", ".", "--no-deps", "--quiet")

NEEDLES = (
    "usearch: OK",
    "fts5: OK",
    "embedding model: OK",
    "file watcher: OK",
    "window chrome: OK",
    "time zones: OK",
    "mcp sdk: OK",
)


class HelperError(Exception):
    """A refusal or environment failure. ``code`` is the exit code (2 refusal)."""

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Pure core: paths
# ---------------------------------------------------------------------------

_MNT_RE = re.compile(r"^/mnt/([a-zA-Z])(?:/|$)(.*)$")


def to_win_path(path: str, cwd: str = "C:\\Windows\\System32") -> str:
    """Lexically normalise a path of any form the flight lists to a canonical
    Windows path: ``/mnt/c/..``, ``\\\\?\\`` prefixes, ``\\\\wsl.localhost\\..``
    (kept as UNC), ``..`` segments, trailing dots and spaces, mixed separators,
    relative paths (resolved against ``cwd``)."""
    s = str(path)
    m = _MNT_RE.match(s) if s.startswith("/") else None
    if m:
        s = m.group(1).upper() + ":\\" + m.group(2)
    s = s.replace("/", "\\")
    low = s.lower()
    if low.startswith("\\\\?\\unc\\"):
        s = "\\\\" + s[8:]
    elif low.startswith("\\\\?\\") or low.startswith("\\\\.\\"):
        s = s[4:]
    unc = s.startswith("\\\\")
    if not unc and not re.match(r"^[A-Za-z]:", s):
        base = cwd.replace("/", "\\")
        if s.startswith("\\"):
            s = base[:2] + s
        else:
            s = base.rstrip("\\") + "\\" + s
    prefix = ""
    rest = s
    if unc:
        prefix = "\\\\"
        rest = s[2:]
    elif re.match(r"^[A-Za-z]:", s):
        prefix = s[0].upper() + ":\\"
        rest = s[2:]
    comps: list[str] = []
    for c in rest.split("\\"):
        if c in ("", "."):
            continue
        if c == "..":
            if comps:
                comps.pop()
            continue
        c = c.rstrip(". ")
        if c:
            comps.append(c)
    return prefix + "\\".join(comps)


def path_components(path: str, cwd: str = "C:\\Windows\\System32") -> list[str]:
    norm = to_win_path(path, cwd)
    unc = norm.startswith("\\\\")
    body = norm[2:] if unc else norm
    comps = [c for c in body.split("\\") if c]
    out = [c.casefold() for c in comps]
    if unc:
        out.insert(0, "\\\\")
    return out


def is_within(child: str, parent: str) -> bool:
    """True when ``child`` equals or sits inside ``parent`` (by components)."""
    c, p = path_components(child), path_components(parent)
    return len(c) >= len(p) and c[: len(p)] == p


def path_overlap(a: str, b: str) -> str | None:
    """'equal' / 'inside' (a inside b) / 'contains' (a contains b) / None."""
    ca, cb = path_components(a), path_components(b)
    n = min(len(ca), len(cb))
    if ca[:n] != cb[:n]:
        return None
    if len(ca) == len(cb):
        return "equal"
    return "inside" if len(ca) > len(cb) else "contains"


def check_data_dir(
    data_dir_forms: list[str], operator_forms: list[str], root_forms: list[str]
) -> None:
    """Refuse a data dir that equals, sits inside or contains the operator's data
    dir (any lexical or resolved form of either), or that lies outside the scratch
    root (every form of the target must be inside some form of the root)."""
    for d in data_dir_forms:
        for o in operator_forms:
            why = path_overlap(d, o)
            if why:
                raise HelperError(
                    f"refusing data dir {d!r}: it {'is' if why == 'equal' else why} the "
                    f"operator's data dir {o!r} (rule: never touch the operator's data)"
                )
    for d in data_dir_forms:
        if not any(is_within(d, r) for r in root_forms):
            raise HelperError(
                f"refusing data dir {d!r}: it is outside the scratch root {root_forms[0]!r} "
                "(rule: scratch data dirs live under the root)"
            )


def validate_root(root: str, localappdata: str, operator_forms: list[str]) -> str:
    """A valid scratch root is under ``%LOCALAPPDATA%\\Temp``, has a leaf matching
    ``the-one-f5*`` and does not equal, contain or sit inside the operator's data
    dir. Returns the normalised root."""
    norm = to_win_path(root)
    temp = to_win_path(localappdata) + "\\Temp"
    comps = path_components(norm)
    if not is_within(norm, temp) or path_overlap(norm, temp) in ("equal", "contains"):
        raise HelperError(
            f"refusing root {norm!r}: it must be under {temp!r} (rule: scratch root in Temp)"
        )
    if not comps[-1].startswith(ROOT_LEAF_PREFIX):
        raise HelperError(
            f"refusing root {norm!r}: leaf must match {ROOT_LEAF_PREFIX}* (rule: root leaf)"
        )
    for o in operator_forms:
        why = path_overlap(norm, o)
        if why:
            raise HelperError(f"refusing root {norm!r}: it {why} the operator's data dir {o!r}")
    return norm


def assert_within(real_target: str, real_root: str) -> None:
    if not is_within(real_target, real_root):
        raise HelperError(
            f"refusing write outside the scratch root: {real_target!r} is not inside {real_root!r}"
        )


# ---------------------------------------------------------------------------
# Pure core: ports
# ---------------------------------------------------------------------------


def check_port(
    port: int,
    kind: str,
    excluded: list[tuple[int, int]],
    busy: set[int],
) -> None:
    """Refuse a port: the operator's 8484, the preview 8485, anything below 8490
    (app) or 9390 (CDP), an excluded range, or a port with a listener."""
    if port in FORBIDDEN_PORTS:
        raise HelperError(f"refusing port {port}: that is {FORBIDDEN_PORTS[port]}")
    minimum = MIN_CDP_PORT if kind == "cdp" else MIN_APP_PORT
    if port < minimum:
        raise HelperError(f"refusing port {port}: {kind} ports start at {minimum}")
    for lo, hi in excluded:
        if lo <= port <= hi:
            raise HelperError(f"refusing port {port}: inside the excluded range {lo}-{hi}")
    if port in busy:
        raise HelperError(f"refusing port {port}: something is already listening on it")


# ---------------------------------------------------------------------------
# Pure core: process identity (tables are plain dicts, no ctypes)
# ---------------------------------------------------------------------------
# A table maps pid -> {"pid","ppid","create" (int), "path","cmd"}.


def identity_matches(record: dict, live: dict | None) -> bool:
    """A live process is the recorded one only if pid, creation time and path all
    match (a reused PID has a different creation time)."""
    if not live:
        return False
    return (
        record["pid"] == live["pid"]
        and record["create"] == live["create"]
        and str(record["path"]).casefold() == str(live["path"]).casefold()
    )


def kill_allowed_path(path: str, allowed_dirs: list[str]) -> bool:
    return bool(path) and any(is_within(path, d) for d in allowed_dirs if d)


def check_kill(record: dict, live: dict | None, allowed_dirs: list[str]) -> tuple[bool, str]:
    """(ok, reason). The live process must match the record AND lie under the
    scratch root, the base interpreter dir or the WebView2 runtime dir."""
    if live is None:
        return False, "gone"
    if not identity_matches(record, live):
        return False, "identity-mismatch"
    if not kill_allowed_path(live["path"], allowed_dirs):
        return False, "path-not-allowed"
    return True, "ok"


def children_map(table: dict[int, dict]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for pid, p in table.items():
        out.setdefault(p["ppid"], []).append(pid)
    return out


def descendants(table: dict[int, dict], seeds: set[int]) -> dict[int, int]:
    """child pid -> parent pid for every live descendant of ``seeds``. A process
    counts as a child only if it was created at or after its parent, so a reused
    parent PID cannot adopt unrelated processes."""
    kids = children_map(table)
    found: dict[int, int] = {}
    queue = [s for s in seeds if s in table]
    seen = set(queue)
    while queue:
        cur = queue.pop()
        for k in kids.get(cur, []):
            if k in seen or k == cur:
                continue
            if table[k]["create"] < table[cur]["create"]:
                continue
            seen.add(k)
            found[k] = cur
            queue.append(k)
    return found


_UDD_RE = re.compile(r'--user-data-dir=(?:"([^"]*)"|(\S+))', re.IGNORECASE)


def webview_by_data_dir(table: dict[int, dict], data_dir: str) -> set[int]:
    """Processes whose command line carries ``--user-data-dir=`` pointing inside
    ``data_dir`` (how WebView2 processes are found once their parent has died)."""
    out: set[int] = set()
    for pid, p in table.items():
        m = _UDD_RE.search(p.get("cmd") or "")
        if not m:
            continue
        if is_within(m.group(1) or m.group(2), data_dir):
            out.add(pid)
    return out


def merge_members(
    members: list[dict], table: dict[int, dict], data_dir: str
) -> tuple[list[dict], list[dict]]:
    """Fold newly found descendants and user-data-dir matches into the recorded
    members. Returns (all members, members still live by identity)."""
    by_pid = {m["pid"]: m for m in members}
    live_pids = {m["pid"] for m in members if identity_matches(m, table.get(m["pid"]))}
    merged = list(members)
    recorded = {(m["pid"], m["create"]) for m in members}
    for child, parent in descendants(table, set(live_pids)).items():
        if (child, table[child]["create"]) in recorded:
            continue
        role = by_pid.get(parent, {}).get("role", "app")
        entry = {
            "pid": child,
            "create": table[child]["create"],
            "path": table[child]["path"],
            "role": role,
        }
        merged.append(entry)
        by_pid[child] = entry
        recorded.add((child, entry["create"]))
        live_pids.add(child)
    for pid in webview_by_data_dir(table, data_dir):
        if (pid, table[pid]["create"]) in recorded:
            continue
        entry = {
            "pid": pid,
            "create": table[pid]["create"],
            "path": table[pid]["path"],
            "role": "webview",
        }
        merged.append(entry)
        recorded.add((pid, entry["create"]))
        live_pids.add(pid)
    live = [m for m in merged if identity_matches(m, table.get(m["pid"]))]
    return merged, live


def kill_order(live: list[dict]) -> list[dict]:
    """Interpreter first (never the venv launcher alone), then the other app
    members, then WebView2 leftovers, the watchdog last."""

    def key(m: dict) -> tuple[int, int]:
        role = m.get("role", "app")
        if role == "watchdog":
            return (3, 0)
        if role == "webview":
            return (2, 0)
        return (0, 0) if is_within(m["path"], BASE_PYTHON_DIR) else (1, 0)

    return sorted(live, key=key)


def find_installed_app(
    table: dict[int, dict],
    listeners: list[dict],
    root: str,
    recorded_paths: list[str],
    port: int = INSTALLED_PORT,
) -> dict:
    """The installed app is the owner of the port-8484 listener whose executable
    path is not under the scratch root and not in any recorded tree. Never chosen
    by name. 'Not running' is a classification, not an error."""
    owners = sorted({lst["pid"] for lst in listeners if lst["port"] == port})
    if not owners:
        return {"state": "not-running"}
    for pid in owners:
        p = table.get(pid)
        if not p or not p.get("path"):
            return {"state": "unknown-owner", "pid": pid}
        if root and is_within(p["path"], root):
            continue
        if any(str(p["path"]).casefold() == str(r).casefold() for r in recorded_paths):
            continue
        return {"state": "running", "pid": pid, "create": p["create"], "path": p["path"]}
    return {"state": "not-running"}


# ---------------------------------------------------------------------------
# Pure core: snapshot diff
# ---------------------------------------------------------------------------


def compare_snapshots(before: dict, after: dict) -> dict:
    """Classify the differences between two snapshots. Returns
    {"ok", "allowed": [...], "failures": [...], "info": [...]}. Allowed (reported,
    not judged): geometry saved by the operator's own close or tray
    (window-state.json), and a new installed-app PID after the operator restarted
    it. Anything else, a new top-level entry name or an environment change fails."""
    allowed: list[str] = []
    failures: list[str] = []
    info: list[str] = []
    bi, ai = before.get("installed", {}), after.get("installed", {})
    if (bi.get("pid"), bi.get("create")) != (ai.get("pid"), ai.get("create")):
        allowed.append(
            f"installed app changed: {bi.get('state')} pid {bi.get('pid')} -> "
            f"{ai.get('state')} pid {ai.get('pid')} (operator restarted or closed it)"
        )
    bf, af = before.get("files", {}), after.get("files", {})
    for name in sorted(set(bf) | set(af)):
        b, a = bf.get(name), af.get(name)
        if b == a:
            continue
        if name == "window-state.json" and (a or {}).get("exists") and (b or {}).get("exists"):
            allowed.append("window-state.json changed (geometry saved by the operator's own app)")
            continue
        failures.append(f"operator file {name} changed: {b} -> {a}")
    be, ae = set(before.get("entries", [])), set(after.get("entries", []))
    for name in sorted(ae - be):
        failures.append(f"new top-level entry in the operator's data dir: {name}")
    for name in sorted(be - ae):
        info.append(f"top-level entry gone from the operator's data dir: {name}")
    if before.get("env") != after.get("env"):
        failures.append(f"environment changed: {before.get('env')} -> {after.get('env')}")
    return {"ok": not failures, "allowed": allowed, "failures": failures, "info": info}


# ---------------------------------------------------------------------------
# Pure core: hands-off rule
# ---------------------------------------------------------------------------


def tick_age(now: int, then: int) -> int:
    """Elapsed ms between two 32-bit tick counts, wraparound-safe."""
    return (now - then) & TICK_MASK


def operator_input_recent(
    last_input_tick: int,
    last_injection_tick: int | None,
    now: int,
    window_ms: int = HANDS_OFF_WINDOW_MS,
) -> bool:
    """True when the OPERATOR gave input within ``window_ms``. Input is the
    operator's only if it is newer than the helper's own last injection (None =
    no injection, e.g. a missing last-injection file)."""
    if tick_age(now, last_input_tick) >= window_ms:
        return False
    if last_injection_tick is None:
        return True
    delta = (last_input_tick - last_injection_tick) & TICK_MASK
    newer = 0 < delta < 0x80000000
    return newer


def parse_last_injection(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        return int(text.strip()) & TICK_MASK
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Pure core: sync planning, environment
# ---------------------------------------------------------------------------


def is_protected(rel: str) -> bool:
    parts = [p for p in re.split(r"[\\/]", rel) if p]
    return any(p in SYNC_PROTECTED_PARTS or p.endswith(SYNC_PROTECTED_SUFFIXES) for p in parts)


def plan_sync(
    src: dict[str, tuple[int, float]],
    dest: dict[str, tuple[int, float]],
    prev_manifest: list[str],
) -> dict[str, list[str]]:
    """``src``/``dest`` map relative path -> (size, mtime). Copy what is missing or
    differs; delete only files listed in the previous manifest that are no longer in
    the current list, and never anything protected (dist, build, *.egg-info,
    __pycache__)."""
    copy = [
        rel
        for rel, (size, mtime) in sorted(src.items())
        if rel not in dest or dest[rel][0] != size or abs(dest[rel][1] - mtime) > 1.5
    ]
    delete = [
        rel
        for rel in sorted(prev_manifest)
        if rel not in src and not is_protected(rel) and rel in dest
    ]
    return {"copy": copy, "delete": delete}


def scrub_env(
    environ: dict[str, str], port: int, data_dir: str, cdp_port: int | None
) -> dict[str, str]:
    """The child environment: every inherited THE_ONE_* and WEBVIEW2_* variable is
    removed, then THE_ONE_PORT, THE_ONE_DATA_DIR and (only with a CDP port) the
    WebView2 debugging argument are set."""
    env = {k: v for k, v in environ.items() if not k.upper().startswith(ENV_PREFIXES)}
    env["THE_ONE_PORT"] = str(port)
    env["THE_ONE_DATA_DIR"] = data_dir
    if cdp_port is not None:
        env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={cdp_port}"
    return env


def parse_doctor(output: str, code: int) -> dict:
    gates = [ln for ln in output.splitlines() if re.match(r"^\s{2}[^:]+: (OK|FAIL) ", ln)]
    result = next((ln.strip() for ln in output.splitlines() if ln.startswith("RESULT:")), None)
    return {
        "exit_code": code,
        "result_line": result,
        "gate_count": len(gates),
        "gates": [g.strip() for g in gates],
        "needles": {n: (n in output) for n in NEEDLES},
    }


def parse_excluded_ranges(text: str) -> list[tuple[int, int]]:
    out = []
    for ln in text.splitlines():
        m = re.match(r"^\s*(\d+)\s+(\d+)\s*\*?\s*$", ln)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    return out


def parse_listeners(text: str) -> list[dict]:
    out = []
    for ln in text.splitlines():
        parts = ln.strip().split("|")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            out.append({"addr": parts[0], "port": int(parts[1]), "pid": int(parts[2])})
    return out


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# Scratch-root writes (used by both halves): sentinel + resolved-target check
# ---------------------------------------------------------------------------


def local_path(win: str) -> str:
    """A path the current OS can open: identity on Windows, /mnt/<d>/ on WSL."""
    if os.name == "nt":
        return win
    m = re.match(r"^([A-Za-z]):\\?(.*)$", win)
    if not m:
        raise HelperError(f"cannot map {win!r} into WSL")
    return "/mnt/" + m.group(1).lower() + "/" + m.group(2).replace("\\", "/")


def win_from_local(p: str) -> str:
    return to_win_path(p)


def real_win(win: str) -> str:
    """The resolved Windows form of ``win`` (symlinks and junctions followed on the
    longest existing ancestor; trailing components kept)."""
    return win_from_local(os.path.realpath(local_path(win)))


def guard(root: str, target: str) -> str:
    """Require the sentinel and that the RESOLVED target stays inside the RESOLVED
    root; returns the local path to use."""
    if not os.path.isfile(local_path(root + "\\" + SENTINEL)):
        raise HelperError(f"refusing: {root!r} has no {SENTINEL} sentinel (not a scratch root)")
    assert_within(real_win(target), real_win(root))
    return local_path(target)


def g_write(root: str, target: str, data: str, append: bool = False) -> None:
    p = guard(root, target)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a" if append else "w", encoding="utf-8", newline="\n") as f:
        f.write(data)


def g_mkdirs(root: str, target: str) -> None:
    os.makedirs(guard(root, target), exist_ok=True)


def g_read(root: str, target: str) -> str | None:
    p = guard(root, target)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def g_remove(root: str, target: str) -> None:
    p = guard(root, target)
    try:
        os.remove(p)
    except FileNotFoundError:
        pass


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def venv_python(root: str, windowed: bool = False) -> str:
    return root + "\\venv\\Scripts\\" + ("pythonw.exe" if windowed else "python.exe")


def frozen_dir(root: str) -> str:
    return root + "\\src\\dist\\the-one"


def tree_file(root: str, tree_id: str) -> str:
    return root + "\\pids\\" + tree_id + ".json"


# ---------------------------------------------------------------------------
# Pure core (leg 1b): gate selection, key grammar, geometry, captures, focus
# ---------------------------------------------------------------------------

RESERVED_TREE_IDS = ("own", "own-b")
INTERFERENCE_TOLERANCE_MS = 16
CAPTION_HEIGHT_PX = 31
CAPTION_BUTTONS_WIDTH_PX = 138  # three 46px buttons at 96 DPI
SNAP_MARGIN_PX = 12
CAPTION_MOVE_TOLERANCE_PX = 4
SERIES_MAX_FRAMES = 200
SERIES_MIN_INTERVAL_MS = 16
SERIES_MAX_BYTES = 256 * 1024 * 1024
OWN_DEFAULT_SECONDS = 60
OWN_MAX_SECONDS = 600
OWN_SIZE = (200, 100)
TOPMOST_MAX_SECONDS = 60
CMD_ALLOWLIST = ("front-tree", "restore-focus")
CMD_TTL_S = 5.0
FOCUS_STALE_S = 2 * 3600
OWN_IDS = ("a", "b")
# The technique `front` and `focus-restore` use when none is named (premise 13).
DECIDED_TECHNIQUE = "own"
TECHNIQUES = ("own", "switch", "topmost", "minrestore", "sfw-helper")


def select_gate_pids(trees: dict[str, list[int]], target_id: str | None) -> tuple[str, set[int]]:
    """The one gate tree: the tree named by ``target_id``, else the single recorded
    tree (refused when there are several). The own windows' records are never
    trees; a tree id that is reserved for them is skipped."""
    cands = {tid: pids for tid, pids in trees.items() if tid not in RESERVED_TREE_IDS}
    if target_id is not None:
        if target_id in RESERVED_TREE_IDS:
            raise HelperError(f"refusing tree id {target_id!r}: reserved for the own windows")
        if target_id not in cands:
            raise HelperError(f"no recorded tree {target_id!r} (rule: one gate tree)")
        tid = target_id
    elif len(cands) == 1:
        tid = next(iter(cands))
    elif not cands:
        raise HelperError("no recorded tree: run `launch` first (rule: one gate tree)")
    else:
        raise HelperError(
            f"several recorded trees {sorted(cands)}: name one with --tree-id (rule: one gate tree)"
        )
    pids = {int(p) for p in cands[tid]}
    if not pids:
        raise HelperError(f"tree {tid!r} has no live process (rule: one gate tree)")
    return tid, pids


# ----------------------------- key grammar ---------------------------------

_MODS = {"^": "ctrl", "+": "shift", "%": "alt"}
NAMED_KEYS: dict[str, int] = {
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "TAB": 0x09,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "BACKSPACE": 0x08,
    "BS": 0x08,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "INSERT": 0x2D,
    "INS": 0x2D,
    "HOME": 0x24,
    "END": 0x23,
    "PGUP": 0x21,
    "PGDN": 0x22,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
    "SPACE": 0x20,
}
NAMED_KEYS.update({f"F{n}": 0x70 + n - 1 for n in range(1, 13)})
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}
_WIN_NAMES = {"WIN", "LWIN", "RWIN", "WINDOWS", "SUPER", "META", "CMD", "COMMAND"}
_PRTSC_NAMES = {"PRTSC", "PRTSCR", "PRINTSCREEN", "SNAPSHOT", "PRINT", "SYSRQ"}
_DENY_PREFIXES = ("VOLUME", "MEDIA", "BROWSER", "LAUNCH", "SLEEP", "POWER", "WAKE")


class KeySpecError(HelperError):
    """A key spec the grammar refuses or cannot parse (exit 2, nothing sent)."""


def parse_keys(spec: str) -> list[dict]:
    """Parse the small key grammar into steps ``{"mods": [...], "key": str,
    "named": bool}``: ``^`` Ctrl, ``+`` Shift, ``%`` Alt (each applies to the next
    key), ``{NAME}`` a named key, plain text, and ``{^}`` ``{+}`` ``{%}`` ``{{}``
    ``{}}`` for those characters typed literally. Refuses any Win key, Alt+Tab,
    Alt+Esc, Ctrl+Esc, Ctrl+Shift+Esc, Alt+F4, Ctrl+Alt+anything, PrintScreen,
    media/volume/browser/launch keys and any F-key with Alt or Win."""
    if not spec:
        raise KeySpecError("malformed key spec: empty")
    steps: list[dict] = []
    mods: list[str] = []
    i = 0
    while i < len(spec):
        c = spec[i]
        if c in _MODS:
            m = _MODS[c]
            if m not in mods:
                mods.append(m)
            i += 1
            continue
        named = False
        if c == "{":
            if spec[i : i + 3] in ("{{}", "{}}"):
                key = spec[i + 1]
                i += 3
            else:
                j = spec.find("}", i + 1)
                if j < 0:
                    raise KeySpecError(f"malformed key spec {spec!r}: unclosed '{{'")
                name = spec[i + 1 : j]
                if not name:
                    raise KeySpecError(f"malformed key spec {spec!r}: empty '{{}}'")
                i = j + 1
                if name in _MODS:
                    key = name
                else:
                    up = name.upper()
                    if up in _WIN_NAMES:
                        raise KeySpecError(f"refused key {name!r}: Win key (rule: no Win key)")
                    if up in _PRTSC_NAMES:
                        raise KeySpecError(f"refused key {name!r}: PrintScreen")
                    if up.startswith(_DENY_PREFIXES):
                        raise KeySpecError(f"refused key {name!r}: media/browser/launch key")
                    if up not in NAMED_KEYS:
                        raise KeySpecError(f"malformed key spec {spec!r}: unknown key {name!r}")
                    key, named = up, True
        else:
            key = c
            i += 1
        step = {"mods": sorted(mods), "key": key, "named": named}
        _refuse_combo(step)
        steps.append(step)
        mods = []
    if mods:
        raise KeySpecError(f"malformed key spec {spec!r}: trailing modifier")
    return steps


def _refuse_combo(step: dict) -> None:
    mods, key, named = set(step["mods"]), step["key"], step["named"]
    if {"ctrl", "alt"} <= mods:
        raise KeySpecError("refused combo: Ctrl+Alt+anything (rule: no Ctrl+Alt)")
    if named and "alt" in mods and key in ("TAB", "ESC", "ESCAPE"):
        raise KeySpecError(f"refused combo: Alt+{key} (rule: no window switching)")
    if named and "ctrl" in mods and key in ("ESC", "ESCAPE"):
        raise KeySpecError(
            "refused combo: Ctrl+Esc and Ctrl+Shift+Esc (rule: no Start/Task Manager)"
        )
    if named and "alt" in mods and re.fullmatch(r"F\d+", key):
        raise KeySpecError(
            f"refused combo: Alt+{key} (rule: no Alt+F-keys; close the copy with its x or `stop`)"
        )


def key_events(steps_vk: list[tuple[list[int], int, bool]]) -> list[tuple[int, bool]]:
    """Expand ``(modifier vks, key vk, extended)`` steps to ``(vk, down)`` events:
    modifiers down in order, key down and up, modifiers up in reverse."""
    out: list[tuple[int, bool]] = []
    for mod_vks, vk, _ext in steps_vk:
        out += [(m, True) for m in mod_vks]
        out += [(vk, True), (vk, False)]
        out += [(m, False) for m in reversed(mod_vks)]
    return out


# ----------------------------- geometry ------------------------------------
# A rect is [left, top, right, bottom], right and bottom exclusive.


def point_in_rect(p, r) -> bool:
    return r[0] <= p[0] < r[2] and r[1] <= p[1] < r[3]


def rect_inside(inner, outer) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )


def rects_intersect(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def xywh_to_rect(x: int, y: int, w: int, h: int) -> list[int]:
    return [x, y, x + w, y + h]


def caption_zone(frame, dpi: int = 96) -> list[int]:
    """The draggable caption strip of a window with DWM frame bounds ``frame``:
    the top 31px (scaled) left of the three caption buttons."""
    s = (dpi or 96) / 96
    return [
        frame[0],
        frame[1],
        frame[2] - round(CAPTION_BUTTONS_WIDTH_PX * s),
        frame[1] + round(CAPTION_HEIGHT_PX * s),
    ]


def plan_caption_drag(start, end, frame, work, dpi: int = 96) -> dict:
    """Plan a caption drag: the start is on the caption strip, the post-move frame
    bounds lie inside the monitor's work area (the end point no nearer than
    ``SNAP_MARGIN_PX`` to its edge, so no snap fires), and the end lies inside the
    post-move bounds. Refuses otherwise (``KeySpecError`` is not used: plain
    ``HelperError``)."""
    if not point_in_rect(start, caption_zone(frame, dpi)):
        raise HelperError(
            f"refusing drag: start {tuple(start)} is not on the window's caption "
            "(rule: caption drags start on the caption, left of its buttons)"
        )
    dx, dy = end[0] - start[0], end[1] - start[1]
    planned = [frame[0] + dx, frame[1] + dy, frame[2] + dx, frame[3] + dy]
    if not rect_inside(planned, work):
        raise HelperError(
            f"refusing drag: the moved window {planned} would leave the work area {list(work)} "
            "(rule: drags stay inside the monitor)"
        )
    if not point_in_rect(end, planned):
        raise HelperError("refusing drag: the end point is outside the moved window")
    inner = [
        work[0] + SNAP_MARGIN_PX,
        work[1] + SNAP_MARGIN_PX,
        work[2] - SNAP_MARGIN_PX,
        work[3] - SNAP_MARGIN_PX,
    ]
    if not point_in_rect(end, inner):
        raise HelperError(
            f"refusing drag: end {tuple(end)} is within {SNAP_MARGIN_PX}px of the screen edge "
            "(rule: no snap-to-edge; the operator checks snapping)"
        )
    return {"mode": "caption", "delta": [dx, dy], "planned": planned}


RESIZE_MIN = 100
RESIZE_MAX = 10000


def validate_resize(width, height) -> tuple[int, int]:
    """The outer size ``resize`` may ask for: integers in [RESIZE_MIN, RESIZE_MAX]."""
    out = []
    for name, v in (("width", width), ("height", height)):
        if isinstance(v, bool) or not isinstance(v, int):
            raise HelperError(f"resize --{name} must be an integer, got {v!r}")
        if v < RESIZE_MIN or v > RESIZE_MAX:
            raise HelperError(f"resize --{name} {v} is outside {RESIZE_MIN}..{RESIZE_MAX}")
        out.append(v)
    return out[0], out[1]


def plan_content_drag(start, end, frame) -> dict:
    """Plan a content or resize drag: start and end both inside the gate window's
    CURRENT frame bounds."""
    if not point_in_rect(start, frame):
        raise HelperError(f"refusing drag: start {tuple(start)} is outside the window")
    if not point_in_rect(end, frame):
        raise HelperError(
            f"refusing drag: end {tuple(end)} is outside the window's bounds {list(frame)} "
            "(rule: a drag may not end over an operator window)"
        )
    return {"mode": "content", "delta": [end[0] - start[0], end[1] - start[1]]}


def drag_path(start, end, steps: int) -> list[tuple[int, int]]:
    steps = max(1, int(steps))
    return [
        (
            round(start[0] + (end[0] - start[0]) * i / steps),
            round(start[1] + (end[1] - start[1]) * i / steps),
        )
        for i in range(1, steps + 1)
    ]


def gate_point_decision(
    root_hwnd: int | None,
    root_pid: int | None,
    gate_pids: set[int],
    own_hwnds: set[int],
    allow_own: bool,
) -> str:
    """Classify the window under a point: ``tree`` (the gate tree), ``own`` (an
    identity-checked own window, only when ``allow_own``). Anything else, or
    nothing, raises a refusal."""
    if root_hwnd is None or root_pid is None:
        raise HelperError("refusing: no window under the point (rule: pointer gate)")
    if root_pid in gate_pids:
        return "tree"
    if allow_own and root_hwnd in own_hwnds:
        return "own"
    raise HelperError(
        f"refusing: the window under the point (pid {root_pid}) is not the gate tree"
        + (" or an own window" if allow_own else "")
        + " (rule: pointer gate)"
    )


# ----------------------------- captures ------------------------------------


def capture_contained(rect, areas) -> bool:
    return any(a and rect_inside(rect, a) for a in areas)


def z_above(windows: list[dict], target_hwnd: int) -> list[dict] | None:
    """The windows earlier than the target in EnumWindows (top-to-bottom) order, or
    None when the target is not listed."""
    for i, w in enumerate(windows):
        if w["hwnd"] == target_hwnd:
            return windows[:i]
    return None


def occluders(above: list[dict], rect, gate_pids: set[int], own_pids: set[int]) -> list[dict]:
    """Windows above the target that cover part of ``rect``. Skipped: invisible,
    cloaked, zero-size, ``WS_EX_TRANSPARENT`` and zero-alpha layered windows."""
    out = []
    for w in above:
        if not w.get("visible") or w.get("cloaked"):
            continue
        b = w["bounds"]
        if b[2] <= b[0] or b[3] <= b[1]:
            continue
        if w.get("transparent") or w.get("alpha") == 0:
            continue
        if not rects_intersect(b, rect):
            continue
        if w["pid"] in own_pids:
            kind = "covered_by_own"
        elif w["pid"] in gate_pids:
            kind = "covered_by_tree"
        else:
            kind = "covered_by_other"
        out.append({"hwnd": w["hwnd"], "pid": w["pid"], "kind": kind})
    return out


def target_translucent(entry: dict) -> bool:
    """A layered target below full alpha shows what is behind it, which may be the
    operator's windows: its pixels are not the test copy's."""
    alpha = entry.get("alpha")
    return alpha is not None and alpha < 255


def occlusion_verdict(occ: list[dict], allow_own_cover: bool = False) -> dict:
    """``ok`` is False when any window covers the rect, except that
    ``allow_own_cover`` accepts a rect covered only by the helper's own windows
    (the pixels are then the helper's, and the verdict says so)."""
    if not occ:
        return {"ok": True, "reason": None, "own_cover_allowed": False}
    kinds = {o["kind"] for o in occ}
    if kinds == {"covered_by_own"} and allow_own_cover:
        return {"ok": True, "reason": None, "own_cover_allowed": True}
    for k in ("covered_by_other", "covered_by_tree", "covered_by_own"):
        if k in kinds:
            return {"ok": False, "reason": k, "own_cover_allowed": False}
    return {"ok": True, "reason": None, "own_cover_allowed": False}


def check_series(frames: int, interval_ms: float, width: int, height: int) -> None:
    if not 1 <= frames <= SERIES_MAX_FRAMES:
        raise HelperError(f"refusing series: frames must be 1..{SERIES_MAX_FRAMES} (got {frames})")
    if interval_ms < SERIES_MIN_INTERVAL_MS:
        raise HelperError(
            f"refusing series: interval must be at least {SERIES_MIN_INTERVAL_MS} ms "
            f"(got {interval_ms})"
        )
    total = frames * width * height * 4
    if total > SERIES_MAX_BYTES:
        raise HelperError(
            f"refusing series: {frames} frames of {width}x{height} need {total} bytes "
            f"(limit {SERIES_MAX_BYTES}); use a smaller --rect"
        )


def max_series_frames(width: int, height: int) -> int:
    return max(0, min(SERIES_MAX_FRAMES, SERIES_MAX_BYTES // max(1, width * height * 4)))


def _lin(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def contrast_ratio(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def patch_stats(pixels: list[tuple[int, int, int]]) -> dict:
    """Mean RGB plus the darkest and lightest pixel (by relative luminance)."""
    if not pixels:
        raise HelperError("empty patch")
    n = len(pixels)
    mean = [round(sum(p[i] for p in pixels) / n, 2) for i in range(3)]
    dark = min(pixels, key=luminance)
    light = max(pixels, key=luminance)
    return {"mean": mean, "darkest": list(dark), "lightest": list(light), "n": n}


def bgra_pixels(buf: bytes, w: int, h: int) -> list[tuple[int, int, int]]:
    return [(buf[i + 2], buf[i + 1], buf[i]) for i in range(0, w * h * 4, 4)]


def bgra_mean(buf: bytes) -> list[float]:
    n = len(buf) // 4
    if not n:
        return [0.0, 0.0, 0.0]
    return [
        round(sum(buf[2::4]) / n, 2),
        round(sum(buf[1::4]) / n, 2),
        round(sum(buf[0::4]) / n, 2),
    ]


def bgra_to_rgb(buf: bytes) -> bytes:
    n = len(buf) // 4
    out = bytearray(n * 3)
    out[0::3] = buf[2::4]
    out[1::3] = buf[1::4]
    out[2::3] = buf[0::4]
    return bytes(out)


def encode_png(width: int, height: int, rgb: bytes) -> bytes:
    """A minimal 8-bit RGB PNG (stdlib only)."""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    stride = width * 3
    raw = b"".join(b"\x00" + rgb[y * stride : (y + 1) * stride] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


# ----------------------------- own window ----------------------------------


def clamp_own_seconds(value: float | None, default: int = OWN_DEFAULT_SECONDS) -> int:
    if value is None:
        return default
    return int(max(1, min(OWN_MAX_SECONDS, value)))


def clamp_topmost_seconds(value: float | None) -> int:
    if value is None:
        return TOPMOST_MAX_SECONDS
    return int(max(1, min(TOPMOST_MAX_SECONDS, value)))


def place_own_window(work, size=OWN_SIZE, at=None) -> list[int]:
    """The own window's rect: the bottom-left corner of the work area by default,
    or ``at`` (x, y); always clamped inside the work area."""
    w, h = size
    if at is None:
        x, y = work[0] + 8, work[3] - h - 8
    else:
        x, y = at
    x = max(work[0], min(x, work[2] - w))
    y = max(work[1], min(y, work[3] - h))
    return [x, y, x + w, y + h]


def make_command(action: str, nonce: str, now: float, params: dict | None = None) -> dict:
    return {
        "action": action,
        "nonce": nonce,
        "expires": now + CMD_TTL_S,
        "params": params or {},
    }


def validate_command(cmd: dict, now: float, seen: set[str]) -> tuple[bool, str]:
    """(ok, reason) for a command read from the own window's channel. Only the
    allowlisted actions run; an expired or repeated nonce is ignored."""
    if not isinstance(cmd, dict):
        return False, "malformed"
    if cmd.get("action") not in CMD_ALLOWLIST:
        return False, "not-allowed"
    nonce = cmd.get("nonce")
    if not nonce or not isinstance(nonce, str):
        return False, "no-nonce"
    if nonce in seen:
        return False, "repeated-nonce"
    exp = cmd.get("expires")
    if not isinstance(exp, (int, float)) or now > exp:
        return False, "expired"
    if exp > now + 2 * CMD_TTL_S:
        return False, "bad-expiry"
    return True, "ok"


# ----------------------------- injection record ----------------------------


def record_injection(send, read_tick, write) -> int:
    """Send one batch, THEN read the tick, THEN write it, so the helper's own input
    never counts as the operator's."""
    send()
    tick = read_tick()
    write(tick)
    return tick


def injection_interference(
    last_input_tick: int,
    own_last_tick: int | None,
    tolerance: int = INTERFERENCE_TOLERANCE_MS,
) -> bool:
    """True when input newer than the helper's own last tick (by more than one timer
    tick) arrived mid-gesture: the operator's. Wraparound-safe."""
    if own_last_tick is None:
        return False
    delta = tick_age(last_input_tick, own_last_tick)
    return tolerance < delta < 0x80000000


def cursor_restore_decision(saved, left_at, now_at) -> str:
    """``restore`` (put the cursor back), ``leave`` (the operator moved it since the
    helper left it) or ``none`` (it is already where it started)."""
    if tuple(now_at) != tuple(left_at):
        return "leave"
    if tuple(saved) == tuple(now_at):
        return "none"
    return "restore"


# ----------------------------- focus ---------------------------------------


def focus_save_decision(
    existing: dict | None,
    existing_live: bool,
    now: float,
    fg_exists: bool,
    fg_is_ours: bool,
    discard: bool = False,
) -> str:
    """``save`` / ``replace-stale`` / ``refuse-fresh-exists`` / ``refuse-ours`` /
    ``refuse-nothing`` / ``discard`` / ``nothing-to-discard``. The first save of a
    session wins; a record is stale when its identity no longer matches or it is
    older than two hours."""
    if discard:
        return "discard" if existing else "nothing-to-discard"
    if fg_is_ours:
        return "refuse-ours"
    if not fg_exists:
        return "refuse-nothing"
    if existing:
        stale = (not existing_live) or (now - existing.get("saved_at", 0)) > FOCUS_STALE_S
        return "replace-stale" if stale else "refuse-fresh-exists"
    return "save"


def focus_restore_decision(
    saved_live: bool, saved_hwnd: int, fg_hwnd: int | None, fg_is_ours: bool
) -> str:
    """``gone`` / ``already-foreground`` / ``operator-moved-on`` / ``restore``. Acts
    only when the foreground is the gate tree, an own window, or nothing."""
    if not saved_live:
        return "gone"
    if fg_hwnd and fg_hwnd == saved_hwnd:
        return "already-foreground"
    if fg_hwnd and not fg_is_ours:
        return "operator-moved-on"
    return "restore"


def focus_restore_outcome(fg_after: int | None, saved_hwnd: int) -> str:
    return "restored" if fg_after and fg_after == saved_hwnd else "failed"


def summarize_input_log(text: str) -> dict:
    """Counts of sent / aborted / refused rows, and the targets of every ``sent``."""
    counts = {"sent": 0, "aborted": 0, "refused": 0}
    targets: dict[str, int] = {}
    for ln in text.splitlines():
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        o = row.get("outcome")
        if o in counts:
            counts[o] += 1
        if o == "sent":
            t = row.get("target", "?")
            targets[t] = targets.get(t, 0) + 1
    return {**counts, "sent_targets": targets}


def dangling_row(text: str) -> dict | None:
    """The last row of ``input.log`` when it is a ``begin`` with no outcome row after
    it (a gesture in progress, or one whose helper died), else None."""
    rows = [ln for ln in text.splitlines() if ln.strip()]
    if not rows:
        return None
    try:
        row = json.loads(rows[-1])
    except ValueError:
        return None
    return row if row.get("outcome") == "begin" else None


def log_dangling(text: str) -> bool:
    return dangling_row(text) is not None


# ---------------------------------------------------------------------------
# --- Windows half: ctypes, winreg, subprocess (stdlib only, lazy)
# ---------------------------------------------------------------------------

PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
TH32CS_SNAPPROCESS = 0x2


class _FILETIME(ctypes.Structure):
    _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


_W: dict = {}


def _api() -> dict:
    """Lazily bind the Win32 functions (never at import: the module loads on Linux)."""
    if _W:
        return _W
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    nt = ctypes.WinDLL("ntdll")
    dwm = ctypes.WinDLL("dwmapi")
    hnd = ctypes.c_void_p
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = hnd
    k32.CloseHandle.argtypes = [hnd]
    k32.GetProcessTimes.argtypes = [hnd] + [ctypes.POINTER(_FILETIME)] * 4
    k32.QueryFullProcessImageNameW.argtypes = [
        hnd,
        wintypes.DWORD,
        ctypes.c_wchar_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    k32.TerminateProcess.argtypes = [hnd, wintypes.UINT]
    k32.GetExitCodeProcess.argtypes = [hnd, ctypes.POINTER(wintypes.DWORD)]
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.CreateToolhelp32Snapshot.restype = hnd
    k32.Process32FirstW.argtypes = [hnd, ctypes.POINTER(_PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [hnd, ctypes.POINTER(_PROCESSENTRY32W)]
    k32.GetTickCount.restype = wintypes.DWORD
    nt.NtQueryInformationProcess.argtypes = [
        hnd,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.POINTER(wintypes.ULONG),
    ]
    nt.NtQueryInformationProcess.restype = ctypes.c_long
    u32.GetForegroundWindow.restype = hnd
    u32.GetWindowThreadProcessId.argtypes = [hnd, ctypes.POINTER(wintypes.DWORD)]
    u32.GetWindowTextW.argtypes = [hnd, ctypes.c_wchar_p, ctypes.c_int]
    u32.GetClassNameW.argtypes = [hnd, ctypes.c_wchar_p, ctypes.c_int]
    u32.IsWindowVisible.argtypes = [hnd]
    u32.GetWindowRect.argtypes = [hnd, ctypes.POINTER(wintypes.RECT)]
    u32.GetClientRect.argtypes = [hnd, ctypes.POINTER(wintypes.RECT)]
    u32.ClientToScreen.argtypes = [hnd, ctypes.POINTER(wintypes.POINT)]
    u32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    u32.OpenInputDesktop.restype = hnd
    u32.CloseDesktop.argtypes = [hnd]
    u32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, hnd, wintypes.LPARAM)
    u32.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]
    dwm.DwmGetWindowAttribute.argtypes = [hnd, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _W.update(k32=k32, u32=u32, nt=nt, dwm=dwm, enum_proc=enum_proc)
    try:  # real pixels for rects; affects only this helper process
        u32.SetProcessDpiAwarenessContext.argtypes = [hnd]
        u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass
    return _W


def _handle_identity(h) -> tuple[int, str]:
    w = _api()
    c, e, kt, ut = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
    create = 0
    if w["k32"].GetProcessTimes(h, c, e, kt, ut):
        create = (c.hi << 32) | c.lo
    buf = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(buf))
    path = buf.value if w["k32"].QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) else ""
    return create, path


def _handle_cmdline(h) -> str:
    w = _api()
    need = wintypes.ULONG(0)
    w["nt"].NtQueryInformationProcess(h, 60, None, 0, ctypes.byref(need))
    if not need.value:
        return ""
    buf = ctypes.create_string_buffer(need.value + 16)
    st = w["nt"].NtQueryInformationProcess(h, 60, buf, len(buf), ctypes.byref(need))
    if st != 0:
        return ""
    length = int.from_bytes(buf.raw[0:2], "little")
    ptr = int.from_bytes(buf.raw[8:16], "little")
    off = ptr - ctypes.addressof(buf)
    if length <= 0 or off < 0 or off + length > len(buf):
        return ""
    return buf.raw[off : off + length].decode("utf-16-le", "replace")


def proc_table() -> dict[int, dict]:
    """The process table from ONE source (ctypes: Toolhelp parents, OpenProcess
    identity, NtQueryInformationProcess command lines)."""
    w = _api()
    snap = w["k32"].CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    table: dict[int, dict] = {}
    entry = _PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    ok = w["k32"].Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        pid = entry.th32ProcessID
        table[pid] = {
            "pid": pid,
            "ppid": entry.th32ParentProcessID,
            "name": entry.szExeFile,
            "create": 0,
            "path": "",
            "cmd": "",
        }
        ok = w["k32"].Process32NextW(snap, ctypes.byref(entry))
    w["k32"].CloseHandle(snap)
    for pid, p in table.items():
        if pid == 0:
            continue
        h = w["k32"].OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            continue
        try:
            p["create"], p["path"] = _handle_identity(h)
            if p["name"].lower().startswith("msedge"):
                p["cmd"] = _handle_cmdline(h)
        finally:
            w["k32"].CloseHandle(h)
    return table


def _kill_one(member: dict, allowed_dirs: list[str]) -> str:
    """One handle for check and kill, so a reused PID can never be killed."""
    w = _api()
    h = w["k32"].OpenProcess(
        PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION, False, member["pid"]
    )
    if not h:
        err = ctypes.get_last_error()
        return "gone" if err == 87 else f"refused:open-failed({err})"
    try:
        code = wintypes.DWORD(0)
        if w["k32"].GetExitCodeProcess(h, ctypes.byref(code)) and code.value != STILL_ACTIVE:
            return "gone"
        create, path = _handle_identity(h)
        live = {"pid": member["pid"], "create": create, "path": path}
        ok, why = check_kill(member, live, allowed_dirs)
        if not ok:
            return "gone" if why == "gone" else f"refused:{why}"
        return "killed" if w["k32"].TerminateProcess(h, 1) else "refused:terminate-failed"
    finally:
        w["k32"].CloseHandle(h)


def _ps(script: str, timeout: int = 60) -> str:
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    out = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            enc,
        ],
        capture_output=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
        cwd="C:\\Windows",
    )
    return out.stdout.decode("utf-8", "replace")


def listeners() -> list[dict]:
    text = _ps(
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | "
        'ForEach-Object { "$($_.LocalAddress)|$($_.LocalPort)|$($_.OwningProcess)" }'
    )
    return parse_listeners(text)


def excluded_ranges() -> list[tuple[int, int]]:
    out = subprocess.run(
        ["netsh", "int", "ipv4", "show", "excludedportrange", "protocol=tcp"],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        cwd="C:\\Windows",
    )
    return parse_excluded_ranges(out.stdout.decode("utf-8", "replace"))


def _reg_value(hive, subkey: str, name: str, view=0):
    import winreg

    try:
        with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | view) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _reg_env(hive, subkey: str) -> dict[str, str]:
    import winreg

    out: dict[str, str] = {}
    try:
        with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as k:
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                i += 1
                if name.upper().startswith(ENV_PREFIXES):
                    out[name] = str(val)
    except OSError:
        pass
    return out


def env_levels() -> dict:
    import winreg

    return {
        "user": _reg_env(winreg.HKEY_CURRENT_USER, "Environment"),
        "machine": _reg_env(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    }


def last_input() -> dict:
    w = _api()
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    w["u32"].GetLastInputInfo(ctypes.byref(info))
    return {"last_input": int(info.dwTime), "now": int(w["k32"].GetTickCount())}


def session_locked(table: dict[int, dict]) -> dict:
    w = _api()
    desk = w["u32"].OpenInputDesktop(0, False, 0x0100)
    if desk:
        w["u32"].CloseDesktop(desk)
    logon = any(p.get("name", "").lower() == "logonui.exe" for p in table.values())
    return {"input_desktop_null": not bool(desk), "logonui_running": logon}


def _scrubbed_environ(extra: dict | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(ENV_PREFIXES)}
    env.update(extra or {})
    return env


def host_paths() -> dict:
    la = os.environ.get("LOCALAPPDATA", "")
    return {"localappdata": to_win_path(la), "temp": to_win_path(la) + "\\Temp"}


def resolve_forms(path: str) -> list[str]:
    lex = to_win_path(path)
    forms = [lex]
    real = to_win_path(os.path.realpath(lex))
    if real.casefold() != lex.casefold():
        forms.append(real)
    return forms


def operator_forms(root: str | None) -> dict:
    """The operator's data dir. Before the venv exists: %LOCALAPPDATA%\\the-one
    (cross-check pending). After setup: platformdirs in the venv, cross-checked;
    any mismatch stops the helper."""
    lexical = to_win_path(os.environ["LOCALAPPDATA"] + "\\the-one")
    status = "pending"
    py = venv_python(root) if root else ""
    if py and os.path.isfile(py):
        env = _scrubbed_environ()
        proc = subprocess.run(
            [
                py,
                "-c",
                "import platformdirs;print(platformdirs.user_data_dir('the-one', appauthor=False))",
            ],
            capture_output=True,
            env=env,
            stdin=subprocess.DEVNULL,
            cwd="C:\\Windows",
            timeout=60,
        )
        got = proc.stdout.decode("utf-8", "replace").strip().splitlines()
        if proc.returncode != 0 or not got:
            raise HelperError("cannot resolve the operator's data dir through platformdirs")
        if to_win_path(got[-1]).casefold() != lexical.casefold():
            raise HelperError(
                f"operator data dir mismatch: platformdirs says {got[-1]!r}, "
                f"expected {lexical!r} (stopping rather than guessing)"
            )
        status = "ok"
    forms = resolve_forms(lexical)
    return {"dir": lexical, "forms": forms, "crosscheck": status}


def _tree_ids(root: str) -> list[str]:
    d = local_path(root + "\\pids")
    if not os.path.isdir(d):
        return []
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))


def _load_tree(root: str, tree_id: str) -> dict | None:
    text = g_read(root, tree_file(root, tree_id))
    return json.loads(text) if text else None


def _save_tree(root: str, rec: dict) -> None:
    g_write(root, tree_file(root, rec["tree_id"]), json.dumps(rec, indent=1))


def _allowed_dirs(root: str) -> list[str]:
    """Where a recorded process may live to be killed: the scratch root, the base
    interpreter (the venv's real interpreter) and the WebView2 runtime."""
    dirs = [root, BASE_PYTHON_DIR]
    for var, default in (
        ("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        ("ProgramFiles", "C:\\Program Files"),
    ):
        dirs.append(
            to_win_path(os.environ.get(var, default) + "\\Microsoft\\EdgeWebView\\Application")
        )
    return dirs


def _refresh(root: str, tree_id: str, table: dict | None = None) -> tuple[dict | None, list[dict]]:
    rec = _load_tree(root, tree_id)
    if rec is None:
        return None, []
    table = table if table is not None else proc_table()
    rec["members"], live = merge_members(rec["members"], table, rec["data_dir"])
    _save_tree(root, rec)
    return rec, live


def _audit(root: str, actor: str, member: dict, result: str) -> None:
    line = json.dumps(
        {
            "t": utc_now(),
            "actor": actor,
            "pid": member["pid"],
            "create": member["create"],
            "path": member["path"],
            "role": member.get("role"),
            "result": result,
        }
    )
    g_write(root, root + "\\audit.log", line + "\n", append=True)


# ----------------------------- ops -----------------------------------------


def op_host_paths(a: dict) -> dict:
    return host_paths()


def op_operator_forms(a: dict) -> dict:
    return operator_forms(a.get("root"))


def op_doctor_host(a: dict) -> dict:
    import winreg

    table = proc_table()
    w = _api()
    pv = _reg_value(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "pv",
    ) or _reg_value(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "pv",
    )
    pf = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    wv_dir = f"{pf}\\Microsoft\\EdgeWebView\\Application\\{pv}" if pv else None
    nt = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    pers = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    wv = sys.getwindowsversion()
    op = operator_forms(a.get("root"))
    dpi = None
    try:
        dpi = int(w["u32"].GetDpiForSystem())
    except (AttributeError, OSError):
        pass
    return {
        "build": {
            "CurrentBuild": _reg_value(winreg.HKEY_LOCAL_MACHINE, nt, "CurrentBuild"),
            "UBR": _reg_value(winreg.HKEY_LOCAL_MACHINE, nt, "UBR"),
            "DisplayVersion": _reg_value(winreg.HKEY_LOCAL_MACHINE, nt, "DisplayVersion"),
            "platform_version": getattr(wv, "platform_version", None),
        },
        "webview2": {
            "version": pv,
            "dir": wv_dir,
            "dir_exists": bool(wv_dir and os.path.isdir(wv_dir)),
        },
        "dpi": dpi,
        "AppsUseLightTheme": _reg_value(winreg.HKEY_CURRENT_USER, pers, "AppsUseLightTheme"),
        "SystemUsesLightTheme": _reg_value(winreg.HKEY_CURRENT_USER, pers, "SystemUsesLightTheme"),
        "EnableTransparency": _reg_value(winreg.HKEY_CURRENT_USER, pers, "EnableTransparency"),
        "DWM_ColorPrevalence": _reg_value(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM", "ColorPrevalence"
        ),
        "env": env_levels(),
        "session_locked": session_locked(table),
        "excluded_port_ranges": excluded_ranges(),
        "LongPathsEnabled": _reg_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
            "LongPathsEnabled",
        ),
        "operator_data_dir": op,
        "session_id": _session_id(),
        "paths": host_paths(),
    }


def _session_id() -> int | None:
    try:
        sid = wintypes.DWORD()
        _api()["k32"].ProcessIdToSessionId(os.getpid(), ctypes.byref(sid))
        return int(sid.value)
    except (AttributeError, OSError):
        return None


def op_snapshot(a: dict) -> dict:
    root = a.get("root")
    table = proc_table()
    recorded: list[str] = []
    if root and os.path.isdir(local_path(root + "\\pids")):
        for tid in _tree_ids(root):
            rec = _load_tree(root, tid)
            recorded += [m["path"] for m in (rec or {}).get("members", [])]
    installed = find_installed_app(table, listeners(), root or "", recorded)
    op = operator_forms(root)
    d = local_path(op["dir"])
    files = {}
    for name in OPERATOR_FILES:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            files[name] = {
                "exists": True,
                "mtime_ns": os.stat(p).st_mtime_ns,
                "sha256": sha256_file(p),
            }
        else:
            files[name] = {"exists": False}
    entries = sorted(os.listdir(d)) if os.path.isdir(d) else []
    return {
        "taken": utc_now(),
        "installed": installed,
        "files": files,
        "entries": entries,
        "env": env_levels(),
        "operator_data_dir": op["dir"],
        "crosscheck": op["crosscheck"],
    }


def op_hands_off(a: dict) -> dict:
    """Wait (up to ``timeout`` s) until the operator has not given input recently."""
    root = a["root"]
    inj = parse_last_injection(g_read(root, root + "\\last-injection")) if root else None
    deadline = time.time() + a.get("timeout", HANDS_OFF_WAIT_S)
    waited = False
    while True:
        li = last_input()
        if not operator_input_recent(li["last_input"], inj, li["now"]):
            return {"clear": True, "waited": waited}
        waited = True
        if time.time() >= deadline:
            raise HelperError(
                "operator input is recent (hands-off rule): waited "
                f"{a.get('timeout', HANDS_OFF_WAIT_S)}s",
                code=3,
            )
        time.sleep(0.5)


def _require_ok_root(root: str) -> None:
    if not os.path.isfile(local_path(root + "\\" + SENTINEL)):
        raise HelperError(
            f"{root!r} has no {SENTINEL}: run `setup` first (Storage Sense may have purged it)"
        )


def _validate_dirs_and_ports(a: dict, need_ports: bool) -> dict:
    root = a["root"]
    op = operator_forms(root)
    root_forms = resolve_forms(root)
    dd_forms = resolve_forms(a["data_dir"])
    check_data_dir(dd_forms, op["forms"], root_forms)
    if need_ports:
        excl = excluded_ranges()
        busy = {lst["port"] for lst in listeners()} | set(a.get("ss_busy", []))
        check_port(a["port"], "app", excl, busy)
        if a.get("cdp_port") is not None:
            check_port(a["cdp_port"], "cdp", excl, busy)
    return op


def _env_file_refusal(a: dict, op: dict) -> None:
    if a.get("frozen") and os.path.isfile(os.path.join(local_path(op["dir"]), ".env")):
        raise HelperError(
            "refusing a frozen run: the operator's data dir holds a .env, which a frozen "
            "build reads whatever THE_ONE_DATA_DIR says (rule: .env)"
        )


def _http_get(url: str, headers: dict | None = None, timeout: float = 3.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return r.status, r.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, OSError):
        return 0, ""


def op_launch(a: dict) -> dict:
    root, tree_id = a["root"], a["tree_id"]
    _require_ok_root(root)
    if tree_id in RESERVED_TREE_IDS:
        raise HelperError(f"refusing tree id {tree_id!r}: reserved for the own windows")
    if a.get("frozen") and a.get("script"):
        raise HelperError("--frozen and --script are exclusive")
    op = _validate_dirs_and_ports(a, need_ports=True)
    _env_file_refusal(a, op)
    # A live recorded tree blocks a launch (run stop first).
    table = proc_table()
    for tid in _tree_ids(root):
        if tid in RESERVED_TREE_IDS or (a.get("tree_id_given") and tid != tree_id):
            continue
        rec, live = _refresh(root, tid, table)
        if live:
            raise HelperError(f"a recorded tree {tid!r} is still live: run `stop` first")
    op_hands_off({"root": root})
    vpyw = venv_python(root, True)
    if a.get("frozen"):
        exe = frozen_dir(root) + "\\the-one-app.exe"
        if not os.path.isfile(local_path(exe)):
            raise HelperError(f"{exe} missing: run `freeze` (or `setup`) first")
        cmd = [exe]
    else:
        if not os.path.isfile(vpyw):
            raise HelperError(f"{vpyw} missing: run `setup` first")
        if a.get("script"):
            s = a["script"]
            if re.search(r"[\\/]", s):
                raise HelperError("--script must be a bare file name under the scratch spike dir")
            sp = root + "\\spike\\" + s
            if not os.path.isfile(sp):
                raise HelperError(f"{sp} missing: copy the spike script there first")
            cmd = [vpyw, sp]
        else:
            cmd = [vpyw, "-m", "the_one", "app"]
    data_dir = to_win_path(a["data_dir"])
    g_mkdirs(root, data_dir)
    env = scrub_env(dict(os.environ), a["port"], data_dir, a.get("cdp_port"))
    log = open(guard(root, data_dir + "\\launch.log"), "ab")  # noqa: SIM115
    proc = subprocess.Popen(  # noqa: S603
        cmd,
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        close_fds=True,
        creationflags=0x00000200,  # CREATE_NEW_PROCESS_GROUP; no window style, no hiding
    )
    log.close()
    members: list[dict] = []
    w = _api()
    h = w["k32"].OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, proc.pid)
    create, path = _handle_identity(h)
    w["k32"].CloseHandle(h)
    members.append({"pid": proc.pid, "create": create, "path": path, "role": "app"})
    rec = {
        "tree_id": tree_id,
        "port": a["port"],
        "cdp_port": a.get("cdp_port"),
        "data_dir": data_dir,
        "frozen": bool(a.get("frozen")),
        "script": a.get("script"),
        "started": utc_now(),
        "max_minutes": a.get("max_minutes", 30),
        "members": members,
    }
    _save_tree(root, rec)
    _start_watchdog(root, rec, a["helper_source"], vpyw, env)
    result = {"tree_id": tree_id, "launcher_pid": proc.pid, "cmd": cmd}
    if a.get("script"):
        time.sleep(2)
        _refresh(root, tree_id)
        return result
    cred = local_path(data_dir + "\\api-credential")
    deadline = time.time() + a.get("serve_timeout", 150)
    live_ok = False
    while time.time() < deadline:
        _refresh(root, tree_id)
        if proc.poll() is not None and not live_ok:
            tail = ""
            try:
                with open(
                    local_path(data_dir + "\\launch.log"), encoding="utf-8", errors="replace"
                ) as f:
                    tail = f.read()[-1500:]
            except OSError:
                pass
            raise HelperError(f"the app exited early (code {proc.returncode}): {tail}")
        st, _ = _http_get(f"http://127.0.0.1:{a['port']}/api/live")
        if st == 200:
            live_ok = True
            if os.path.isfile(cred):
                token = open(cred, encoding="utf-8").read().strip()
                st2, body = _http_get(
                    f"http://127.0.0.1:{a['port']}/api/info", {"Authorization": f"Bearer {token}"}
                )
                if st2 == 200:
                    result.update(live=200, info=200, info_body=body[:80])
                    return result
        time.sleep(1.0)
    raise HelperError("the copy did not answer /api/live and /api/info before the timeout", code=2)


def _start_watchdog(root: str, rec: dict, helper_source: str, vpyw: str, env: dict) -> None:
    tid = rec["tree_id"]
    helper = root + "\\pids\\helper-win.py"
    g_write(root, helper, helper_source)
    req = json.dumps({"op": "stop", "args": {"root": root, "tree_id": tid, "actor": "watchdog"}})
    out = root + "\\pids\\watchdog-" + tid + ".out"
    script = (
        "import time\n"
        f"time.sleep({int(rec['max_minutes']) * 60})\n"
        f"src = open({helper!r}, encoding='utf-8').read()\n"
        f"g = {{'__name__': '__main__', '_WIN_REQUEST': {req!r}, '_WIN_OUT': {out!r}}}\n"
        "exec(compile(src, 'helper', 'exec'), g)\n"
    )
    wd = root + "\\pids\\watchdog-" + tid + ".py"
    g_write(root, wd, script)
    p = subprocess.Popen(  # noqa: S603
        [vpyw, wd],
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=0x00000200,
    )
    w = _api()
    h = w["k32"].OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, p.pid)
    create, path = _handle_identity(h)
    w["k32"].CloseHandle(h)
    rec["members"].append({"pid": p.pid, "create": create, "path": path, "role": "watchdog"})
    _save_tree(root, rec)


def _selected_trees(root: str, tree_id: str | None) -> list[str]:
    ids = _tree_ids(root)
    return [tree_id] if tree_id else ids


def op_tree(a: dict) -> dict:
    root = a["root"]
    _require_ok_root(root)
    table = proc_table()
    out = []
    for tid in _selected_trees(root, a.get("tree_id")):
        rec, live = _refresh(root, tid, table)
        if rec is None:
            continue
        out.append(
            {
                "tree_id": tid,
                "port": rec["port"],
                "cdp_port": rec["cdp_port"],
                "started": rec["started"],
                "live": [
                    {
                        "pid": m["pid"],
                        "ppid": table[m["pid"]]["ppid"],
                        "role": m["role"],
                        "path": m["path"],
                        "create": m["create"],
                    }
                    for m in live
                ],
            }
        )
    return {"trees": out}


def _top_windows(pids: set[int]) -> list[dict]:
    w = _api()
    fg = w["u32"].GetForegroundWindow()
    found: list[dict] = []

    def cb(hwnd, _lp):
        pid = wintypes.DWORD()
        w["u32"].GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        title = ctypes.create_unicode_buffer(512)
        w["u32"].GetWindowTextW(hwnd, title, 512)
        cls = ctypes.create_unicode_buffer(256)
        w["u32"].GetClassNameW(hwnd, cls, 256)
        r = wintypes.RECT()
        w["u32"].GetWindowRect(hwnd, ctypes.byref(r))
        cr = wintypes.RECT()
        w["u32"].GetClientRect(hwnd, ctypes.byref(cr))
        pt = wintypes.POINT(0, 0)
        w["u32"].ClientToScreen(hwnd, ctypes.byref(pt))
        eb = wintypes.RECT()
        has_eb = w["dwm"].DwmGetWindowAttribute(hwnd, 9, ctypes.byref(eb), ctypes.sizeof(eb)) == 0
        found.append(
            {
                "hwnd": int(hwnd or 0),
                "pid": pid.value,
                "title": title.value,
                "class": cls.value,
                "visible": bool(w["u32"].IsWindowVisible(hwnd)),
                "in_front": bool(fg and int(hwnd or 0) == int(fg)),
                "outer": [r.left, r.top, r.right, r.bottom],
                "client": [pt.x, pt.y, pt.x + cr.right, pt.y + cr.bottom],
                "client_size": [cr.right, cr.bottom],
                "frame_bounds": [eb.left, eb.top, eb.right, eb.bottom] if has_eb else None,
            }
        )
        return True

    w["u32"].EnumWindows(w["enum_proc"](cb), 0)
    return found


def op_windows(a: dict) -> dict:
    tr = op_tree(a)
    pids = {m["pid"] for t in tr["trees"] for m in t["live"]}
    return {"windows": _top_windows(pids), "tree_pids": sorted(pids)}


def op_rect(a: dict) -> dict:
    wins = op_windows(a)["windows"]
    mains = [x for x in wins if x["visible"] and x["title"] == MAIN_WINDOW_TITLE]
    if not mains:
        raise HelperError("no visible main window titled exactly " + repr(MAIN_WINDOW_TITLE), 2)
    main = max(
        mains,
        key=lambda x: (x["outer"][2] - x["outer"][0]) * (x["outer"][3] - x["outer"][1]),
    )
    try:
        dpi = int(_api()["u32"].GetDpiForSystem())
    except (AttributeError, OSError):
        dpi = None
    return {"main": main, "dpi": dpi}


def op_stop(a: dict) -> dict:
    root = a["root"]
    actor = a.get("actor", "helper")
    _require_ok_root(root)
    allowed = _allowed_dirs(root)
    self_pids: set[int] = set()
    if actor == "watchdog":  # never kill ourselves or our own ancestry
        table0 = proc_table()
        cur = os.getpid()
        while cur in table0 and cur not in self_pids:
            self_pids.add(cur)
            cur = table0[cur]["ppid"]
    report = []
    timeout = a.get("timeout", 30)
    for tid in _selected_trees(root, a.get("tree_id")):
        rec = _load_tree(root, tid)
        if rec is None:
            continue
        table = proc_table()
        rec, live = _refresh(root, tid, table)
        results = []
        wd_live = [m for m in live if m["role"] == "watchdog"]
        targets = [m for m in kill_order(live) if m["pid"] not in self_pids]
        if actor != "watchdog":
            targets = [m for m in targets if m["role"] != "watchdog"]
        if actor != "watchdog" and any(
            x["in_front"] for x in _top_windows({m["pid"] for m in live})
        ):
            # closing the front window moves the foreground: not while the operator types
            op_hands_off({"root": root, "timeout": a.get("hands_off_timeout", HANDS_OFF_WAIT_S)})
        # app members first, with a short grace for WebView2 to exit on its own
        app_targets = [m for m in targets if m["role"] != "webview"]
        for m in app_targets:
            res = _kill_one(m, allowed)
            _audit(root, actor, m, res)
            results.append({"pid": m["pid"], "role": m["role"], "result": res})
        time.sleep(3)
        table = proc_table()
        rec, live = _refresh(root, tid, table)
        for m in kill_order(live):
            if m["pid"] in self_pids or m["role"] == "watchdog":
                continue
            res = _kill_one(m, allowed)
            _audit(root, actor, m, res)
            results.append({"pid": m["pid"], "role": m["role"], "result": res})
        # wait until every recorded non-watchdog member has exited and ports are free
        deadline = time.time() + timeout
        while True:
            table = proc_table()
            rec, live = _refresh(root, tid, table)
            rest = [m for m in live if m["role"] != "watchdog" and m["pid"] not in self_pids]
            ports = {rec["port"]} | ({rec["cdp_port"]} if rec["cdp_port"] else set())
            busy = ports & {lst["port"] for lst in listeners()}
            if not rest and not busy:
                break
            if time.time() >= deadline:
                report.append(
                    {
                        "tree_id": tid,
                        "complete": False,
                        "timeout": True,
                        "still_live": [m["pid"] for m in rest],
                        "ports_busy": sorted(busy),
                        "killed": results,
                    }
                )
                rec = None
                break
            time.sleep(1.0)
        if rec is None:
            continue
        # the watchdog goes last
        if actor != "watchdog":
            for m in wd_live:
                res = _kill_one(m, allowed)
                _audit(root, actor, m, res)
                results.append({"pid": m["pid"], "role": "watchdog", "result": res})
        for rel in (
            tree_file(root, tid),
            root + "\\pids\\watchdog-" + tid + ".py",
        ):
            g_remove(root, rel)
        report.append({"tree_id": tid, "complete": True, "killed": results})
    out: dict = {"stopped": report}
    if not a.get("tree_id") and actor != "watchdog":
        t = proc_table()
        out["own_closed"] = [_own_close_one(dict(a), oid, t) for oid in OWN_IDS]
    return out


def op_serve_check(a: dict) -> dict:
    st, _ = _http_get(f"http://127.0.0.1:{a['port']}/api/live")
    return {"live": st}


def _run_logged(root: str, log_rel: str, cmd: list[str], cwd: str, env: dict, step: str) -> float:
    t0 = time.time()
    g_write(root, root + "\\logs\\" + log_rel, f"\n=== {utc_now()} {step}: {cmd}\n", append=True)
    lp = guard(root, root + "\\logs\\" + log_rel)
    with open(lp, "ab") as f:
        proc = subprocess.run(  # noqa: S603
            cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT
        )
    dt = time.time() - t0
    g_write(
        root, root + "\\logs\\" + log_rel, f"=== exit {proc.returncode} ({dt:.1f}s)\n", append=True
    )
    if proc.returncode != 0:
        raise HelperError(f"step {step!r} failed with exit {proc.returncode}; see logs\\{log_rel}")
    return dt


def _build_env(root: str, extra: dict | None = None) -> dict:
    env = _scrubbed_environ(
        {
            "PIP_CACHE_DIR": root + "\\cache\\pip",
            "UV_CACHE_DIR": root + "\\cache\\uv",
            "PYINSTALLER_CONFIG_DIR": root + "\\cache\\pyinstaller",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        }
    )
    env.update(extra or {})
    return env


def op_build_venv(a: dict) -> dict:
    root = a["root"]
    _require_ok_root(root)
    src = root + "\\src"
    env = _build_env(root)
    times: dict = {}
    log = "setup.log"
    vpy = venv_python(root)
    if not os.path.isfile(vpy):
        times["venv"] = _run_logged(
            root,
            log,
            [BASE_PYTHON_DIR + "\\python.exe", "-m", "venv", root + "\\venv"],
            root,
            env,
            "venv",
        )
    h = hashlib.sha256()
    for name in ("uv.lock", "pyproject.toml"):
        with open(local_path(src + "\\" + name), "rb") as f:
            h.update(f.read())
    stamp = root + "\\venv\\.f5-closure-stamp"
    if g_read(root, stamp) == h.hexdigest():
        return {"venv": "up-to-date", "times": times}
    times["pip_uv"] = _run_logged(
        root, log, [vpy, "-m", "pip", "install", "uv", "--quiet"], src, env, "pip install uv"
    )
    req = src + "\\release-requirements.txt"
    lp = guard(root, req)
    t0 = time.time()
    with open(lp, "wb") as f:
        proc = subprocess.run(  # noqa: S603
            [vpy, "-m", "uv", "export", *CLOSURE_UV_EXPORT_ARGS],
            cwd=src, env=env, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.PIPE,
        )  # fmt: skip
    if proc.returncode != 0 or os.path.getsize(lp) == 0:
        raise HelperError(
            f"uv export failed ({proc.returncode}): {proc.stderr.decode('utf-8', 'replace')[-500:]}"
        )
    times["uv_export"] = time.time() - t0
    times["pip_closure"] = _run_logged(
        root,
        log,
        [
            vpy,
            "-m",
            "pip",
            "install",
            *(req if a == "{requirements}" else a for a in CLOSURE_PIP_REQUIREMENTS_ARGS),
        ],
        src,
        env,
        "pip install closure",
    )
    times["pip_editable"] = _run_logged(
        root,
        log,
        [vpy, "-m", "pip", "install", *CLOSURE_PIP_EDITABLE_ARGS],
        src,
        env,
        "pip install -e",
    )
    g_write(root, stamp, h.hexdigest())
    return {"venv": "built", "times": times}


def op_freeze(a: dict) -> dict:
    root = a["root"]
    _require_ok_root(root)
    src = root + "\\src"
    vpy = venv_python(root)
    if not os.path.isfile(vpy):
        raise HelperError("no venv: run `setup` first")
    env = _build_env(root)
    times = {}
    log = "freeze.log"
    times["pip_pyinstaller"] = _run_logged(
        root,
        log,
        [vpy, "-m", "pip", "install", "pyinstaller", "--quiet"],
        src,
        env,
        "pip install pyinstaller",
    )
    times["pyinstaller"] = _run_logged(
        root,
        log,
        [vpy, "-m", "PyInstaller", "--noconfirm", "packaging/windows/the-one.spec"],
        src,
        env,
        "PyInstaller",
    )
    exes = {
        n: os.path.isfile(local_path(frozen_dir(root) + "\\" + n))
        for n in ("the-one.exe", "the-one-app.exe")
    }
    if not all(exes.values()):
        raise HelperError(f"freeze produced no exe: {exes}")
    return {"exes": exes, "times": times}


def op_doctor(a: dict) -> dict:
    root = a["root"]
    _require_ok_root(root)
    op = _validate_dirs_and_ports(a, need_ports=False)
    _env_file_refusal(a, op)
    if a.get("frozen"):
        op_hands_off({"root": root})
    data_dir = to_win_path(a["data_dir"])
    g_mkdirs(root, data_dir)
    env = scrub_env(dict(os.environ), 0, data_dir, None)
    del env["THE_ONE_PORT"]
    if a.get("frozen"):
        cmd = [frozen_dir(root) + "\\the-one.exe", "doctor"]
    else:
        cmd = [venv_python(root), "-m", "the_one", "doctor"]
    proc = subprocess.run(  # noqa: S603
        cmd, cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=600
    )
    text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    out = parse_doctor(text, proc.returncode)
    out["tail"] = text[-1500:]
    return out


def op_net(a: dict) -> dict:
    return {
        "listeners": listeners(),
        "excluded": excluded_ranges(),
    }


def op_last_input(a: dict) -> dict:
    return last_input()


def op_resolve(a: dict) -> dict:
    return {"forms": resolve_forms(a["path"])}


# ===========================================================================
# Leg 1b: input, capture, own window, focus (Windows half)
# ===========================================================================

GA_ROOT = 2
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
SW_SHOWNOACTIVATE = 4
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
GWL_EXSTYLE = -20
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
PW_RENDERFULLCONTENT = 2
WM_DESTROY = 0x0002
WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_TIMER = 0x0113
WM_LBUTTONDOWN = 0x0201
SETTLE_S = 0.3
GESTURE_GAP_S = 0.012

_RELEASE_KEYS = (0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C)
_RELEASE_BUTTONS = (
    (0x01, MOUSEEVENTF_LEFTUP),
    (0x02, MOUSEEVENTF_RIGHTUP),
    (0x04, MOUSEEVENTF_MIDDLEUP),
)


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class _PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", ctypes.c_void_p),
        ("fErase", wintypes.BOOL),
        ("rcPaint", wintypes.RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", ctypes.c_ubyte * 32),
    ]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


_WNDPROC = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
    ctypes.c_ssize_t, ctypes.c_void_p, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", ctypes.c_void_p),
    ]


def _ui() -> dict:
    """Bind the extra Win32 functions leg 1b needs (lazily, on top of ``_api``)."""
    w = _api()
    if w.get("ui"):
        return w
    u32, k32, dwm = w["u32"], w["k32"], w["dwm"]
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    hnd, ui, dw = ctypes.c_void_p, wintypes.UINT, wintypes.DWORD
    u32.SendInput.argtypes = [ui, ctypes.POINTER(_INPUT), ctypes.c_int]
    u32.SendInput.restype = ui
    u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    u32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    u32.WindowFromPoint.argtypes = [wintypes.POINT]
    u32.WindowFromPoint.restype = hnd
    u32.GetAncestor.argtypes = [hnd, ui]
    u32.GetAncestor.restype = hnd
    u32.IsWindow.argtypes = [hnd]
    u32.IsIconic.argtypes = [hnd]
    u32.IsZoomed.argtypes = [hnd]
    u32.SetForegroundWindow.argtypes = [hnd]
    u32.SwitchToThisWindow.argtypes = [hnd, wintypes.BOOL]
    u32.ShowWindow.argtypes = [hnd, ctypes.c_int]
    u32.SetWindowPos.argtypes = [hnd, hnd] + [ctypes.c_int] * 4 + [ui]
    u32.GetWindowLongW.argtypes = [hnd, ctypes.c_int]
    u32.GetWindowLongW.restype = ctypes.c_long
    u32.GetLayeredWindowAttributes.argtypes = [
        hnd,
        ctypes.POINTER(wintypes.COLORREF),
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.POINTER(dw),
    ]
    u32.GetDC.argtypes = [hnd]
    u32.GetDC.restype = hnd
    u32.ReleaseDC.argtypes = [hnd, hnd]
    u32.PrintWindow.argtypes = [hnd, hnd, ui]
    u32.MonitorFromWindow.argtypes = [hnd, dw]
    u32.MonitorFromWindow.restype = hnd
    u32.GetMonitorInfoW.argtypes = [hnd, ctypes.POINTER(_MONITORINFO)]
    u32.SystemParametersInfoW.argtypes = [ui, ui, ctypes.c_void_p, ui]
    u32.VkKeyScanW.argtypes = [ctypes.c_wchar]
    u32.VkKeyScanW.restype = ctypes.c_short
    u32.MapVirtualKeyW.argtypes = [ui, ui]
    u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    u32.GetAsyncKeyState.restype = ctypes.c_short
    u32.PostMessageW.argtypes = [hnd, ui, wintypes.WPARAM, wintypes.LPARAM]
    u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u32.FindWindowW.restype = hnd
    u32.DefWindowProcW.argtypes = [hnd, ui, wintypes.WPARAM, wintypes.LPARAM]
    u32.DefWindowProcW.restype = ctypes.c_ssize_t
    u32.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSEXW)]
    u32.RegisterClassExW.restype = wintypes.ATOM
    u32.CreateWindowExW.argtypes = [
        dw,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        dw,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        hnd,
        hnd,
        hnd,
        ctypes.c_void_p,
    ]
    u32.CreateWindowExW.restype = hnd
    u32.DestroyWindow.argtypes = [hnd]
    u32.PostQuitMessage.argtypes = [ctypes.c_int]
    u32.GetMessageW.argtypes = [ctypes.POINTER(_MSG), hnd, ui, ui]
    u32.TranslateMessage.argtypes = [ctypes.POINTER(_MSG)]
    u32.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
    u32.SetTimer.argtypes = [hnd, ctypes.c_size_t, ui, ctypes.c_void_p]
    u32.KillTimer.argtypes = [hnd, ctypes.c_size_t]
    u32.UpdateWindow.argtypes = [hnd]
    u32.BeginPaint.argtypes = [hnd, ctypes.POINTER(_PAINTSTRUCT)]
    u32.BeginPaint.restype = hnd
    u32.EndPaint.argtypes = [hnd, ctypes.POINTER(_PAINTSTRUCT)]
    u32.LoadCursorW.argtypes = [hnd, ctypes.c_void_p]
    u32.LoadCursorW.restype = hnd
    u32.GetWindowRect.argtypes = [hnd, ctypes.POINTER(wintypes.RECT)]
    k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    k32.GetModuleHandleW.restype = hnd
    k32.GetCurrentProcessId.restype = dw
    dwm.DwmGetWindowAttribute.argtypes = [hnd, dw, ctypes.c_void_p, dw]
    gdi.CreateCompatibleDC.argtypes = [hnd]
    gdi.CreateCompatibleDC.restype = hnd
    gdi.CreateCompatibleBitmap.argtypes = [hnd, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = hnd
    gdi.SelectObject.argtypes = [hnd, hnd]
    gdi.SelectObject.restype = hnd
    gdi.BitBlt.argtypes = [hnd] + [ctypes.c_int] * 4 + [hnd, ctypes.c_int, ctypes.c_int, dw]
    gdi.DeleteObject.argtypes = [hnd]
    gdi.DeleteDC.argtypes = [hnd]
    gdi.GetDIBits.argtypes = [
        hnd,
        hnd,
        ui,
        ui,
        ctypes.c_void_p,
        ctypes.POINTER(_BITMAPINFO),
        ui,
    ]
    gdi.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    gdi.CreateSolidBrush.restype = hnd
    gdi.TextOutW.argtypes = [hnd, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
    gdi.SetBkMode.argtypes = [hnd, ctypes.c_int]
    w.update(gdi=gdi, ui=True)
    return w


# ----------------------------- small Win32 helpers -------------------------


def _root_of(h):
    w = _ui()
    return w["u32"].GetAncestor(h, GA_ROOT) or h


def _hwnd_pid(h) -> int:
    pid = wintypes.DWORD()
    _api()["u32"].GetWindowThreadProcessId(h, ctypes.byref(pid))
    return int(pid.value)


def _fg() -> dict | None:
    """The foreground window resolved to its root: ``{"hwnd", "pid"}`` or None."""
    u32 = _ui()["u32"]
    fg = u32.GetForegroundWindow()
    if not fg:
        return None
    root = _root_of(fg)
    return {"hwnd": int(root), "pid": _hwnd_pid(root)}


def _cursor() -> tuple[int, int]:
    pt = wintypes.POINT()
    _ui()["u32"].GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def _point_owner(x: int, y: int) -> tuple[int | None, int | None]:
    u32 = _ui()["u32"]
    h = u32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    if not h:
        return None, None
    root = _root_of(h)
    return int(root), _hwnd_pid(root)


def _frame_of(hwnd) -> list[int]:
    w = _ui()
    eb = wintypes.RECT()
    if w["dwm"].DwmGetWindowAttribute(hwnd, 9, ctypes.byref(eb), ctypes.sizeof(eb)) == 0:
        return [eb.left, eb.top, eb.right, eb.bottom]
    r = wintypes.RECT()
    w["u32"].GetWindowRect(hwnd, ctypes.byref(r))
    return [r.left, r.top, r.right, r.bottom]


def _work_area_for(hwnd) -> list[int]:
    u32 = _ui()["u32"]
    mon = u32.MonitorFromWindow(hwnd, 2)
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    u32.GetMonitorInfoW(mon, ctypes.byref(mi))
    r = mi.rcWork
    return [r.left, r.top, r.right, r.bottom]


def _work_area_primary() -> list[int]:
    r = wintypes.RECT()
    _ui()["u32"].SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA (read)
    return [r.left, r.top, r.right, r.bottom]


def _dpi() -> int:
    try:
        return int(_api()["u32"].GetDpiForSystem())
    except (AttributeError, OSError):
        return 96


def _proc_identity(pid: int) -> dict:
    w = _api()
    h = w["k32"].OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return {"pid": pid, "create": 0, "path": ""}
    try:
        create, path = _handle_identity(h)
    finally:
        w["k32"].CloseHandle(h)
    return {"pid": pid, "create": create, "path": path}


def _class_of(hwnd) -> str:
    cls = ctypes.create_unicode_buffer(256)
    _api()["u32"].GetClassNameW(hwnd, cls, 256)
    return cls.value


# ----------------------------- logs and gesture wrapper --------------------


def _ilog(a: dict, gesture: str, outcome: str, **kw) -> None:
    row = {"t": utc_now(), "run": a.get("run_id"), "gesture": gesture, "outcome": outcome}
    if outcome == "begin":
        ident = _proc_identity(os.getpid())
        row["helper"] = {"pid": ident["pid"], "create": ident["create"], "path": ident["path"]}
    row.update(kw)
    g_write(a["root"], a["root"] + "\\input.log", json.dumps(row) + "\n", append=True)
    if outcome != "begin":
        a["_logged"] = True


def _release_all_inputs() -> dict:
    """Release every modifier and mouse button that reads as held. Safe at any time."""
    w = _ui()
    u32 = w["u32"]
    released = []
    for vk in _RELEASE_KEYS:
        if u32.GetAsyncKeyState(vk) & 0x8000:
            _send_key(vk, False)
            released.append(f"key:{vk:#x}")
    for vk, flag in _RELEASE_BUTTONS:
        if u32.GetAsyncKeyState(vk) & 0x8000:
            _send_mouse(flag)
            released.append(f"button:{vk:#x}")
    return {"released": released}


def _recover(a: dict) -> None:
    """A previous helper call that died mid-gesture leaves a ``begin`` row with no
    outcome: release everything before doing anything else."""
    text = g_read(a["root"], a["root"] + "\\input.log") or ""
    row = dangling_row(text)
    if row is not None:
        owner = row.get("helper")
        if owner and identity_matches(owner, proc_table().get(owner.get("pid"))):
            return  # that gesture's helper is still running: not ours to release
        res = _release_all_inputs()
        _Injector(a).touch()
        _ilog(a, "recover", "ok", released=res["released"])


def _gesture(name: str):
    """Wrap an op: recover, log ``begin``, and log ``refused``/``aborted`` for any
    failure that the op did not log itself."""

    def deco(fn):
        def wrapper(a: dict) -> dict:
            _require_ok_root(a["root"])
            a["_logged"] = False
            _recover(a)
            _ilog(a, name, "begin")
            try:
                res = fn(a)
            except HelperError as e:
                if not a.get("_logged"):
                    _ilog(a, name, "aborted" if e.code == 5 else "refused", rule=str(e)[:300])
                raise
            except BaseException as e:
                if not a.get("_logged"):
                    _ilog(a, name, "aborted", rule=f"{type(e).__name__}: {e}"[:300])
                raise
            if not a.get("_logged"):
                _ilog(a, name, "ok")
            return res

        wrapper.__name__ = fn.__name__
        return wrapper

    return deco


def _hands_off(a: dict) -> None:
    op_hands_off({"root": a["root"], "timeout": a.get("hands_off_timeout", HANDS_OFF_WAIT_S)})


# ----------------------------- raw input -----------------------------------


def _send_inputs(items: list) -> None:
    arr = (_INPUT * len(items))(*items)
    n = _ui()["u32"].SendInput(len(items), arr, ctypes.sizeof(_INPUT))
    if n != len(items):
        raise HelperError(f"SendInput sent {n} of {len(items)} events (blocked?)", code=5)


def _key_input(vk: int, down: bool) -> _INPUT:
    u32 = _ui()["u32"]
    flags = 0 if down else KEYEVENTF_KEYUP
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    ki = _KEYBDINPUT(vk, u32.MapVirtualKeyW(vk, 0), flags, 0, 0)
    return _INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=ki))


def _send_key(vk: int, down: bool) -> None:
    _send_inputs([_key_input(vk, down)])


def _send_mouse(flag: int) -> None:
    mi = _MOUSEINPUT(0, 0, 0, flag, 0, 0)  # no MOUSEEVENTF_MOVE or ABSOLUTE: no coordinates
    _send_inputs([_INPUT(INPUT_MOUSE, _INPUTUNION(mi=mi))])


class _Injector:
    """Per-gesture injection state: hands-off before the first batch, an
    interference check before each later batch, and ``record_injection`` after every
    batch so the helper's own input never reads as the operator's."""

    def __init__(self, a: dict):
        self.a = a
        self.root = a["root"]
        self.own_last: int | None = None
        self.batches = 0

    def _write(self, tick: int) -> None:
        self.own_last = tick
        g_write(self.root, self.root + "\\last-injection", str(tick))

    def before(self) -> None:
        """The hands-off wait (first batch) or the mid-gesture interference check."""
        if self.batches == 0:
            _hands_off(self.a)
            return
        if injection_interference(last_input()["last_input"], self.own_last):
            raise HelperError("operator input arrived mid-gesture (interference)", code=5)

    def send(self, fn) -> None:
        k32 = _api()["k32"]
        record_injection(fn, lambda: int(k32.GetTickCount()), self._write)
        self.batches += 1

    def touch(self) -> None:
        """Record a tick after a non-input action (a cursor restore)."""
        self._write(int(_api()["k32"].GetTickCount()))


def _kind_of(pid: int | None, ctx: dict) -> str:
    if pid is None:
        return "none"
    if pid in ctx["pids"]:
        return "tree"
    if pid in ctx["own_pids"]:
        return "own"
    return "other"


def _gate(a: dict, required: bool = True) -> dict:
    """The gate context: the one gate tree's live pids, the identity-checked own
    windows, and the process table they came from."""
    root = a["root"]
    table = proc_table()
    trees: dict[str, list[int]] = {}
    for tid in _tree_ids(root):
        if tid in RESERVED_TREE_IDS:
            continue
        rec, live = _refresh(root, tid, table)
        if rec is not None:
            trees[tid] = [m["pid"] for m in live if m["role"] != "watchdog"]
    tid: str | None = None
    pids: set[int] = set()
    try:
        tid, pids = select_gate_pids(trees, a.get("tree_id"))
    except HelperError:
        if required:
            raise
    owns = {}
    for oid in OWN_IDS:
        rec = _own_live(root, oid, table)
        if rec:
            owns[oid] = rec
    return {
        "root": root,
        "table": table,
        "tree_id": tid,
        "pids": pids,
        "owns": owns,
        "own_hwnds": {r["hwnd"] for r in owns.values()},
        "own_pids": {r["pid"] for r in owns.values()},
    }


def _main_window(ctx: dict) -> dict | None:
    mains = [
        x for x in _top_windows(ctx["pids"]) if x["visible"] and x["title"] == MAIN_WINDOW_TITLE
    ]
    if not mains:
        return None
    return max(
        mains, key=lambda x: (x["outer"][2] - x["outer"][0]) * (x["outer"][3] - x["outer"][1])
    )


def _need_main(ctx: dict) -> dict:
    m = _main_window(ctx)
    if m is None:
        raise HelperError("no visible main window titled exactly " + repr(MAIN_WINDOW_TITLE), 2)
    return m


def _check_pointer(
    x: int, y: int, ctx: dict, allow_own: bool
) -> tuple[str, int | None, int | None]:
    root_h, pid = _point_owner(x, y)
    kind = gate_point_decision(root_h, pid, ctx["pids"], ctx["own_hwnds"], allow_own)
    return kind, root_h, pid


# ----------------------------- own window records --------------------------


def own_file(root: str, oid: str) -> str:
    return root + ("\\own.json" if oid == "a" else "\\own-b.json")


def own_cmd_file(root: str, oid: str) -> str:
    return root + ("\\own\\cmd.json" if oid == "a" else "\\own\\cmd-b.json")


def _own_live(root: str, oid: str, table: dict | None = None) -> dict | None:
    """The own window's record, only when its process identity and its HWND's owner
    both match (a reused PID or HWND never passes)."""
    text = g_read(root, own_file(root, oid))
    if not text:
        return None
    try:
        rec = json.loads(text)
    except ValueError:
        return None
    table = table if table is not None else proc_table()
    if not identity_matches(rec, table.get(rec.get("pid"))):
        return None
    u32 = _ui()["u32"]
    hw = ctypes.c_void_p(rec["hwnd"])
    if not u32.IsWindow(hw) or _hwnd_pid(hw) != rec["pid"]:
        return None
    return rec


# ----------------------------- windows, captures ---------------------------


def _z_windows() -> list[dict]:
    """Every top-level window in z-order (EnumWindows is top-to-bottom), with what
    the occlusion test needs."""
    w = _ui()
    u32, dwm = w["u32"], w["dwm"]
    out: list[dict] = []

    def cb(hwnd, _lp):
        h = int(hwnd or 0)
        visible = bool(u32.IsWindowVisible(hwnd))
        entry = {"hwnd": h, "pid": _hwnd_pid(hwnd), "visible": visible}
        if visible:
            cl = wintypes.DWORD(0)
            dwm.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cl), 4)
            ex = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            alpha = None
            if ex & WS_EX_LAYERED:
                key, al, fl = wintypes.COLORREF(0), ctypes.c_ubyte(255), wintypes.DWORD(0)
                if u32.GetLayeredWindowAttributes(hwnd, key, al, fl) and fl.value & 2:
                    alpha = int(al.value)
            entry.update(
                cloaked=bool(cl.value),
                bounds=_frame_of(hwnd),
                transparent=bool(ex & WS_EX_TRANSPARENT),
                alpha=alpha,
            )
        else:
            entry["bounds"] = [0, 0, 0, 0]
        out.append(entry)
        return True

    u32.EnumWindows(w["enum_proc"](cb), 0)
    return out


def _occlusion(target_hwnd: int, rect, ctx: dict) -> tuple[list[dict], dict] | None:
    """``(occluders of rect above the target, the target's own entry)``, or None when
    the target is not in the z-order list at all (hidden, closed)."""
    zl = _z_windows()
    above = z_above(zl, target_hwnd)
    if above is None:
        return None
    entry = next(w for w in zl if w["hwnd"] == target_hwnd)
    return occluders(above, rect, ctx["pids"], ctx["own_pids"]), entry


def _grab(x: int, y: int, w_: int, h_: int, print_hwnd=None) -> bytes:
    w = _ui()
    u32, gdi = w["u32"], w["gdi"]
    sdc = u32.GetDC(None)
    mdc = gdi.CreateCompatibleDC(sdc)
    bmp = gdi.CreateCompatibleBitmap(sdc, w_, h_)
    old = gdi.SelectObject(mdc, bmp)
    try:
        if print_hwnd is not None:
            ok = u32.PrintWindow(print_hwnd, mdc, PW_RENDERFULLCONTENT)
        else:
            ok = gdi.BitBlt(mdc, 0, 0, w_, h_, sdc, x, y, SRCCOPY | CAPTUREBLT)
        if not ok:
            raise HelperError("the grab failed (BitBlt/PrintWindow returned 0)", code=1)
        gdi.SelectObject(mdc, old)
        bi = _BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = w_
        bi.bmiHeader.biHeight = -h_
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        buf = ctypes.create_string_buffer(w_ * h_ * 4)
        got = gdi.GetDIBits(mdc, bmp, 0, h_, buf, ctypes.byref(bi), 0)
        if not got:
            raise HelperError("GetDIBits failed", code=1)
        return buf.raw
    finally:
        gdi.DeleteObject(bmp)
        gdi.DeleteDC(mdc)
        u32.ReleaseDC(None, sdc)


def _evidence_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name or ""):
        raise HelperError(f"--out must be a bare file name, not {name!r}")
    return name


def _save_png(root: str, name: str, w_: int, h_: int, bgra: bytes) -> dict:
    rel = root + "\\evidence\\" + name
    png = encode_png(w_, h_, bgra_to_rgb(bgra))
    p = guard(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(png)
    return {"file": rel, "bytes": len(png)}


def _no_lock(ctx: dict) -> None:
    lk = session_locked(ctx["table"])
    if lk["input_desktop_null"] or lk["logonui_running"]:
        raise HelperError("the session looks locked: captures would be black", code=6)


def _capture_target(a: dict, ctx: dict) -> dict:
    """Resolve what to capture: ``{"mode", "hwnd", "rect" (or None for per-frame
    window bounds), "areas" (callable)}``."""
    mode = a["mode"]
    if mode == "own":
        oid = a.get("own_id", "a")
        rec = ctx["owns"].get(oid)
        if not rec:
            raise HelperError(f"no live own window {oid!r} (rule: own-window identity)")
        return {"mode": "own", "hwnd": rec["hwnd"], "oid": oid}
    m = _need_main(ctx)
    return {"mode": mode, "hwnd": m["hwnd"], "main": m}


def _tree_frames(ctx: dict) -> list[tuple[int, list[int]]]:
    """``(hwnd, frame bounds)`` of every visible, non-empty top-level window of the gate
    tree (the main window, the splash, a dialog): all of them are the test copy's own
    pixels. Main window first."""
    wins = [x for x in _top_windows(ctx["pids"]) if x["visible"]]
    out = []
    for x in sorted(wins, key=lambda x: x["title"] != MAIN_WINDOW_TITLE):
        fb = x["frame_bounds"] or x["outer"]
        if fb[2] > fb[0] and fb[3] > fb[1]:
            out.append((x["hwnd"], fb))
    return out


def _areas(ctx: dict) -> list[list[int]]:
    areas = [fb for _h, fb in _tree_frames(ctx)]
    for rec in ctx["owns"].values():
        areas.append(_frame_of(ctx_hwnd(rec["hwnd"])))
    return areas


def ctx_hwnd(h: int):
    return ctypes.c_void_p(h)


def _area_target(rect, ctx: dict) -> int | None:
    """The hwnd of the window whose frame bounds contain ``rect``: a window of the
    test copy (main first) or an own window."""
    for hw, fb in _tree_frames(ctx):
        if rect_inside(rect, fb):
            return hw
    for rec in ctx["owns"].values():
        if rect_inside(rect, _frame_of(ctx_hwnd(rec["hwnd"]))):
            return rec["hwnd"]
    return None


def _grab_checked(
    rect, target_hwnd: int, ctx: dict, allow_own_cover: bool
) -> tuple[bytes | None, dict]:
    """One occlusion-tested grab: the test runs before and after the BitBlt. Returns
    ``(pixels or None, info)``; ``info["status"]`` is ``ok`` or the refusal reason."""
    x, y = rect[0], rect[1]
    w_, h_ = rect[2] - rect[0], rect[3] - rect[1]
    info: dict = {}
    first = _occlusion(target_hwnd, rect, ctx)
    if first is None:
        return None, {"status": "no-window"}
    occ, tentry = first
    if target_translucent(tentry):
        # a translucent target shows what is behind it, which may be the operator's
        return None, {"status": "translucent-target", "alpha": tentry.get("alpha")}
    v = occlusion_verdict(occ, allow_own_cover)
    if not v["ok"]:
        return None, {"status": v["reason"], "occluders": occ}
    buf = _grab(x, y, w_, h_)
    second = _occlusion(target_hwnd, rect, ctx)
    if second is None:
        return None, {"status": "no-window"}
    occ2, tentry2 = second
    if target_translucent(tentry2):
        return None, {"status": "translucent-target", "alpha": tentry2.get("alpha")}
    v2 = occlusion_verdict(occ2, allow_own_cover)
    if not v2["ok"]:
        return None, {"status": v2["reason"], "occluders": occ2}
    if v["own_cover_allowed"] or v2.get("own_cover_allowed"):
        info["own_cover_allowed"] = True
        info["occluders"] = occ or occ2
    info["status"] = "ok"
    return buf, info


def _parse_rect(a: dict) -> list[int]:
    x, y, w_, h_ = a["rect"]
    if w_ <= 0 or h_ <= 0:
        raise HelperError("--rect must have a positive width and height")
    return xywh_to_rect(int(x), int(y), int(w_), int(h_))


@_gesture("capture")
def op_capture(a: dict) -> dict:
    root = a["root"]
    name = _evidence_name(a["out"])
    mode = a["mode"]
    ctx = _gate(a, required=mode != "own")
    _no_lock(ctx)
    if a.get("print_window"):
        if mode == "own":
            raise HelperError("--print-window applies to the test copy's main window")
        m = _need_main(ctx)
        hw = ctx_hwnd(m["hwnd"])
        o = m["outer"]
        w_, h_ = o[2] - o[0], o[3] - o[1]
        buf = _grab(0, 0, w_, h_, print_hwnd=hw)
        res = _save_png(root, name + ".png", w_, h_, buf)
        res.update(
            print_window=True,
            size=[w_, h_],
            occlusion="exempt (PrintWindow renders the window itself)",
            mean=bgra_mean(buf),
        )
        _ilog(
            a,
            "capture",
            "ok",
            target=_kind_of(m["pid"], ctx),
            hwnd=m["hwnd"],
            pid=m["pid"],
            mode="print-window",
        )
        return res
    series = a.get("series")
    if a.get("splash") and not series:
        raise HelperError("--splash applies to --series only")
    if series:
        return _capture_series(a, ctx, name)
    if mode == "rect":
        rect = _parse_rect(a)
        areas = _areas(ctx)
        if not capture_contained(rect, areas):
            raise HelperError(
                f"refusing capture: rect {rect} is not inside the test copy's or an own "
                f"window's frame bounds {areas} (rule: capture containment)"
            )
        hwnd = _area_target(rect, ctx)
    else:
        hwnd = _capture_target(a, ctx)["hwnd"]
        rect = _frame_of(ctx_hwnd(hwnd))
    buf, info = _grab_checked(rect, hwnd, ctx, a.get("allow_own_cover", False))
    pid = _hwnd_pid(ctx_hwnd(hwnd))
    if buf is None:
        raise HelperError(
            f"refusing capture: {info['status']} {info.get('occluders', '')} (rule: occlusion test)"
        )
    w_, h_ = rect[2] - rect[0], rect[3] - rect[1]
    res = _save_png(root, name + ".png", w_, h_, buf)
    res.update(rect=rect, size=[w_, h_], mean=bgra_mean(buf), **info)
    if info.get("own_cover_allowed"):
        res["note"] = (
            "DIAGNOSTIC: the covered pixels are the helper's own window, not the test copy"
        )
    _ilog(a, "capture", "ok", target=_kind_of(pid, ctx), hwnd=hwnd, pid=pid, rect=rect)
    return res


def _capture_series(a: dict, ctx: dict, name: str) -> dict:
    root = a["root"]
    n, interval = int(a["series"]), float(a.get("interval_ms", 20))
    mode = a["mode"]
    fixed = _parse_rect(a) if mode == "rect" else None
    if mode == "own":
        raise HelperError("--series applies to --window or --rect")
    want_title = SPLASH_WINDOW_TITLE if a.get("splash") else MAIN_WINDOW_TITLE
    if fixed is not None:
        w0, h0 = fixed[2] - fixed[0], fixed[3] - fixed[1]
    elif a.get("splash"):
        w0, h0 = 400, 300  # the splash's size; its frame is resolved per frame
    else:
        m0 = _need_main(ctx)
        fb = m0["frame_bounds"] or m0["outer"]
        w0, h0 = fb[2] - fb[0], fb[3] - fb[1]
    check_series(n, interval, w0, h0)
    frames: list[dict] = []
    raw: list[tuple[int, bytes, int, int]] = []
    pids = ctx["pids"]
    t_next = time.perf_counter()
    for i in range(n):
        while True:
            now = time.perf_counter()
            if now >= t_next:
                break
            if t_next - now > 0.003:
                time.sleep(t_next - now - 0.002)
        t = time.perf_counter()
        t_next = t + interval / 1000.0
        m = None
        for x in _top_windows(pids):
            if x["visible"] and x["title"] == want_title:
                m = x
        fr = {"i": i, "t": t}
        if m is None:
            fr["status"] = "no-window"
            frames.append(fr)
            continue
        fb = m["frame_bounds"] or m["outer"]
        rect = fixed if fixed is not None else fb
        if not rect_inside(rect, fb):
            fr["status"] = "outside"
            frames.append(fr)
            continue
        buf, info = _grab_checked(rect, m["hwnd"], ctx, a.get("allow_own_cover", False))
        if buf is None:
            fr["status"] = "tainted:" + info["status"]
            frames.append(fr)
            continue
        fr["status"] = "ok"
        fr["mean"] = bgra_mean(buf)
        fr["rect"] = rect
        if info.get("own_cover_allowed"):
            fr["own_cover_allowed"] = True
        frames.append(fr)
        raw.append((i, buf, rect[2] - rect[0], rect[3] - rect[1]))
    files = {}
    for i, buf, w_, h_ in raw:
        files[i] = _save_png(root, f"{name}-{i:03d}.png", w_, h_, buf)["file"]
    for fr in frames:
        if fr["i"] in files:
            fr["file"] = files[fr["i"]]
    index = {"frames": frames, "interval_ms": interval}
    g_write(root, root + "\\evidence\\" + name + "-index.json", json.dumps(index))
    ok = sum(1 for f in frames if f["status"] == "ok")
    summary: dict = {}
    for f in frames:
        summary[f["status"]] = summary.get(f["status"], 0) + 1
    _ilog(a, "capture", "ok", target="tree", mode="series", frames=n, status_counts=summary)
    return {
        "frames": frames,
        "ok_frames": ok,
        "status_counts": summary,
        "index": name + "-index.json",
    }


@_gesture("pixel")
def op_pixel(a: dict) -> dict:
    ctx = _gate(a, required=False if a.get("own") else True)
    _no_lock(ctx)
    size = int(a.get("size", 9))
    if size < 1 or size > 63:
        raise HelperError("--size must be 1..63")
    x, y = int(a["x"]), int(a["y"])
    rect = [x - size // 2, y - size // 2, x - size // 2 + size, y - size // 2 + size]
    areas = _areas(ctx)
    if not capture_contained(rect, areas):
        raise HelperError(
            f"refusing pixel: patch {rect} is not inside the test copy's or an own window's "
            f"frame bounds {areas} (rule: capture containment)"
        )
    hwnd = _area_target(rect, ctx)
    buf, info = _grab_checked(rect, hwnd, ctx, a.get("allow_own_cover", False))
    if buf is None:
        raise HelperError(f"refusing pixel: {info['status']} (rule: occlusion test)")
    st = patch_stats(bgra_pixels(buf, size, size))
    pid = _hwnd_pid(ctx_hwnd(hwnd))
    _ilog(a, "pixel", "ok", target=_kind_of(pid, ctx), hwnd=hwnd, pid=pid, at=[x, y])
    return {"at": [x, y], "size": size, "rect": rect, **st, **info}


# ----------------------------- keys ----------------------------------------


def _resolve_step(step: dict) -> tuple[list[int], int, bool]:
    """Map a parsed step to ``(modifier vks, key vk, extended)`` on the current
    layout. A character that needs Ctrl or Alt (AltGr) on this layout is refused."""
    mods = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12}
    mod_vks = [mods[m] for m in ("ctrl", "shift", "alt") if m in step["mods"]]
    if step["named"]:
        vk = NAMED_KEYS[step["key"]]
    else:
        r = _ui()["u32"].VkKeyScanW(step["key"])
        if r == -1:
            raise HelperError(f"refused key {step['key']!r}: not on the current layout")
        vk, state = r & 0xFF, (r >> 8) & 0xFF
        if state & 6:
            raise HelperError(f"refused key {step['key']!r}: needs Ctrl/Alt (AltGr) here")
        if state & 1 and 0x10 not in mod_vks:
            mod_vks.append(0x10)
    return mod_vks, vk, vk in EXTENDED_VKS


@_gesture("keys")
def op_keys(a: dict) -> dict:
    steps = parse_keys(a["spec"])  # a refusal here sends nothing and is logged
    resolved = [_resolve_step(s) for s in steps]
    ctx = _gate(a)
    events = key_events(resolved)
    inj = _Injector(a)
    pressed: list[int] = []
    sent = 0
    target = None
    try:
        for vk, down in events:
            if down:
                inj.before()
                fg = _fg()
                kind = _kind_of(fg["pid"] if fg else None, ctx)
                if kind != "tree":
                    why = (
                        f"the foreground is not the gate tree (it is {kind}; "
                        f"hwnd {fg['hwnd'] if fg else None}) (rule: foreground gate)"
                    )
                    raise HelperError(
                        "refusing keys: " + why if sent == 0 else "aborted: " + why,
                        code=2 if sent == 0 else 5,
                    )
                target = fg
                inj.send(lambda v=vk: _send_key(v, True))
                pressed.append(vk)
            else:
                inj.send(lambda v=vk: _send_key(v, False))
                if vk in pressed:
                    pressed.remove(vk)
            sent += 1
            time.sleep(GESTURE_GAP_S)
    finally:
        for vk in reversed(pressed):
            try:
                inj.send(lambda v=vk: _send_key(v, False))
            except Exception:  # noqa: BLE001
                pass
    _ilog(
        a,
        "keys",
        "sent",
        spec=a["spec"],
        target="tree",
        hwnd=target["hwnd"] if target else None,
        pid=target["pid"] if target else None,
        events=sent,
    )
    return {"sent": sent, "spec": a["spec"], "foreground": target}


@_gesture("release-all")
def op_release_all(a: dict) -> dict:
    res = _release_all_inputs()
    _Injector(a).touch()
    _ilog(a, "release-all", "sent", target="none", released=res["released"])
    return res


# ----------------------------- pointer -------------------------------------


def _restore_cursor(a: dict, inj: _Injector, saved, left_at) -> dict:
    u32 = _ui()["u32"]
    now_at = _cursor()
    decision = cursor_restore_decision(saved, left_at, now_at)
    before_input = last_input()["last_input"]
    if decision == "restore":
        u32.SetCursorPos(int(saved[0]), int(saved[1]))
    after_input = last_input()["last_input"]
    out = {
        "decision": decision,
        "cursor_after": list(_cursor()),
        "restore_moved_last_input": (before_input != after_input)
        if decision == "restore"
        else None,
    }
    inj.touch()
    return out


def _click_core(a: dict, ctx: dict, x: int, y: int, double: bool, allow_own: bool = True) -> dict:
    u32 = _ui()["u32"]
    inj = _Injector(a)
    inj.before()  # hands-off, then the gate
    kind, root_h, pid = _check_pointer(x, y, ctx, allow_own)  # before any cursor motion
    saved = _cursor()
    u32.SetCursorPos(int(x), int(y))
    down = False
    try:
        if _cursor() != (x, y):
            raise HelperError("aborted: the cursor is not where the helper put it", code=5)
        kind, root_h, pid = _check_pointer(x, y, ctx, allow_own)
        for n in range(2 if double else 1):
            if n:
                time.sleep(0.08)
                if _cursor() != (x, y):
                    raise HelperError("aborted: the cursor moved mid-double-click", code=5)
                if injection_interference(last_input()["last_input"], inj.own_last):
                    raise HelperError("aborted: operator input arrived mid-gesture", code=5)
            inj.send(lambda: _send_mouse(MOUSEEVENTF_LEFTDOWN))
            down = True
            time.sleep(0.03)
            inj.send(lambda: _send_mouse(MOUSEEVENTF_LEFTUP))
            down = False
    finally:
        if down:
            try:
                _send_mouse(MOUSEEVENTF_LEFTUP)
            except Exception:  # noqa: BLE001
                pass
        res = _restore_cursor(a, inj, saved, (x, y))
    return {
        "before": list(saved),
        "target": [x, y],
        "after": res["cursor_after"],
        "cursor_restore": res,
        "owner": {"kind": kind, "hwnd": root_h, "pid": pid},
    }


@_gesture("click")
def op_click(a: dict) -> dict:
    ctx = _gate(a, required=False)  # with no tree, only an own window can pass the gate
    x, y = int(a["x"]), int(a["y"])
    try:
        out = _click_core(a, ctx, x, y, bool(a.get("double")))
    except HelperError as e:
        if e.code == 2:
            owner = _point_owner(x, y)
            _ilog(
                a,
                "click",
                "refused",
                rule=str(e)[:300],
                at=[x, y],
                hwnd=owner[0],
                pid=owner[1],
                target=_kind_of(owner[1], ctx),
            )
            a["_logged"] = True
        raise
    o = out["owner"]
    _ilog(
        a,
        "click",
        "sent",
        at=[x, y],
        double=bool(a.get("double")),
        hwnd=o["hwnd"],
        pid=o["pid"],
        target=o["kind"],
    )
    return out


@_gesture("drag")
def op_drag(a: dict) -> dict:
    ctx = _gate(a)
    u32 = _ui()["u32"]
    start, end = (int(a["x1"]), int(a["y1"])), (int(a["x2"]), int(a["y2"]))
    caption = bool(a.get("caption"))
    steps = int(a.get("steps", 12))
    m = _need_main(ctx)
    frame = m["frame_bounds"] or m["outer"]
    hwnd = ctx_hwnd(m["hwnd"])
    if caption:
        plan = plan_caption_drag(start, end, frame, _work_area_for(hwnd), _dpi())
    else:
        plan = plan_content_drag(start, end, frame)
    inj = _Injector(a)
    inj.before()  # hands-off first: the gates below must not go stale while it waits
    if not caption:
        # the end point must itself be the gate tree's window, not covered (own windows
        # do not count as a drag end)
        _check_pointer(end[0], end[1], ctx, allow_own=False)
    _check_pointer(start[0], start[1], ctx, allow_own=False)
    saved = _cursor()
    u32.SetCursorPos(*start)
    down = False
    last = start
    result: dict = {}
    try:
        if _cursor() != start:
            raise HelperError("aborted: the cursor is not where the helper put it", code=5)
        _check_pointer(start[0], start[1], ctx, allow_own=False)
        inj.send(lambda: _send_mouse(MOUSEEVENTF_LEFTDOWN))
        down = True
        time.sleep(0.05)
        for pt in drag_path(start, end, steps):
            if injection_interference(last_input()["last_input"], inj.own_last):
                raise HelperError("aborted: operator input arrived mid-drag", code=5)
            u32.SetCursorPos(*pt)
            time.sleep(0.02)
            if _cursor() != pt:
                raise HelperError(f"aborted: the cursor left the planned point {pt}", code=5)
            if not caption:
                _check_pointer(pt[0], pt[1], ctx, allow_own=False)
            last = pt
        time.sleep(0.05)
    finally:
        if down:
            try:
                inj.send(lambda: _send_mouse(MOUSEEVENTF_LEFTUP))
            except Exception:  # noqa: BLE001
                pass
        cur = _restore_cursor(a, inj, saved, last)
    time.sleep(SETTLE_S)
    result.update(
        before=list(saved),
        target=list(end),
        after=cur["cursor_after"],
        cursor_restore=cur,
        plan=plan,
    )
    if caption:
        now_frame = _frame_of(hwnd)
        planned = plan["planned"]
        off = max(abs(now_frame[i] - planned[i]) for i in range(4))
        result["frame_after"] = now_frame
        result["moved_as_planned"] = off <= CAPTION_MOVE_TOLERANCE_PX
        if not result["moved_as_planned"]:
            result["status"] = "moved-unexpectedly"
    _ilog(
        a,
        "drag",
        "sent",
        mode="caption" if caption else "content",
        hwnd=m["hwnd"],
        pid=m["pid"],
        target="tree",
        frm=list(start),
        to=list(end),
    )
    return result


# ----------------------------- window state and focus ----------------------


def _focus_file(root: str) -> str:
    return root + "\\focus.json"


def _ours(root: str, table: dict) -> tuple[set[int], set[int]]:
    """Every live process of any recorded tree, and every live own window hwnd."""
    pids: set[int] = set()
    for tid in _tree_ids(root):
        if tid in RESERVED_TREE_IDS:
            continue
        rec = _load_tree(root, tid)
        if rec:
            pids |= {m["pid"] for m in rec["members"] if identity_matches(m, table.get(m["pid"]))}
    hwnds = set()
    for oid in OWN_IDS:
        r = _own_live(root, oid, table)
        if r:
            hwnds.add(r["hwnd"])
            pids.add(r["pid"])
    return pids, hwnds


def _is_ours(fg: dict | None, pids: set[int]) -> bool:
    return bool(fg) and fg["pid"] in pids


def _saved_live(rec: dict | None, table: dict) -> bool:
    if not rec:
        return False
    live = table.get(rec["pid"])
    if not live or live["create"] != rec["create"]:
        return False
    if str(live["path"]).casefold() != str(rec["path"]).casefold():
        return False
    u32 = _ui()["u32"]
    hw = ctypes.c_void_p(rec["hwnd"])
    return bool(u32.IsWindow(hw)) and _hwnd_pid(hw) == rec["pid"]


@_gesture("focus-save")
def op_focus_save(a: dict) -> dict:
    root = a["root"]
    table = proc_table()
    text = g_read(root, _focus_file(root))
    existing = json.loads(text) if text else None
    pids, _hw = _ours(root, table)
    fg = _fg()
    decision = focus_save_decision(
        existing,
        _saved_live(existing, table),
        time.time(),
        fg is not None,
        _is_ours(fg, pids),
        discard=bool(a.get("discard")),
    )
    if decision == "discard":
        g_remove(root, _focus_file(root))
        return {"decision": decision}
    if decision in ("nothing-to-discard",):
        return {"decision": decision}
    if decision.startswith("refuse"):
        raise HelperError(f"refusing focus-save: {decision} (rule: first save of a session wins)")
    ident = _proc_identity(fg["pid"])
    rec = {
        "hwnd": fg["hwnd"],
        "pid": fg["pid"],
        "create": ident["create"],
        "path": ident["path"],
        "class": _class_of(ctypes.c_void_p(fg["hwnd"])),
        "saved_at": time.time(),
    }
    g_write(root, _focus_file(root), json.dumps(rec))
    return {"decision": decision, "saved": {k: rec[k] for k in ("hwnd", "pid", "class", "path")}}


def _set_foreground(hwnd: int, technique: str) -> None:
    """Apply a focus technique from THIS process (premise 13 candidates 2-4)."""
    u32 = _ui()["u32"]
    hw = ctypes.c_void_p(hwnd)
    if u32.IsIconic(hw):
        u32.ShowWindow(hw, SW_RESTORE)
    if technique == "switch":
        u32.SwitchToThisWindow(hw, True)
    elif technique == "topmost":
        try:
            u32.SetWindowPos(hw, ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        finally:
            u32.SetWindowPos(
                hw,
                ctypes.c_void_p(HWND_NOTOPMOST),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
    elif technique == "minrestore":
        u32.ShowWindow(hw, SW_MINIMIZE)
        time.sleep(0.15)
        u32.ShowWindow(hw, SW_RESTORE)
    elif technique == "sfw-helper":
        u32.SetForegroundWindow(hw)
    else:
        raise HelperError(f"unknown technique {technique!r}")


def _own_front(a: dict, ctx: dict, action: str, params: dict) -> dict:
    """Candidate 1: click own window A (a gated click, so A's process holds the
    foreground right), then ask A's process to act through its command channel."""
    rec = ctx["owns"].get("a")
    if not rec:
        raise HelperError("the `own` technique needs a live own window A (own-window show)")
    fg = _fg()
    clicked = None
    if not fg or fg["hwnd"] != rec["hwnd"]:
        fr = _frame_of(ctx_hwnd(rec["hwnd"]))
        cx, cy = (fr[0] + fr[2]) // 2, (fr[1] + fr[3]) // 2 + 12
        clicked = _click_core(dict(a), ctx, cx, cy, False)
        time.sleep(0.15)
    res = _own_do(a, "a", action, params)
    res["clicked_own"] = bool(clicked)
    return res


@_gesture("front")
def op_front(a: dict) -> dict:
    ctx = _gate(a)
    m = _need_main(ctx)
    technique = a.get("technique") or DECIDED_TECHNIQUE
    if technique not in TECHNIQUES:
        raise HelperError(f"unknown technique {technique!r}")
    _hands_off(a)
    before = _fg()
    res: dict = {"technique": technique, "fg_before": before}
    if technique == "own":
        r = _own_front(a, ctx, "front-tree", {"tree_id": ctx["tree_id"], "technique": "sfw"})
        res["own"] = r
    else:
        _set_foreground(m["hwnd"], technique)
    time.sleep(SETTLE_S)
    fg = _fg()
    res["fg_after"] = fg
    res["in_front"] = bool(fg and fg["hwnd"] == m["hwnd"])
    _ilog(
        a,
        "front",
        "sent",
        target="tree",
        hwnd=m["hwnd"],
        pid=m["pid"],
        technique=technique,
        in_front=res["in_front"],
    )
    return res


@_gesture("show-window")
def op_show_window(a: dict) -> dict:
    ctx = _gate(a)
    m = _need_main(ctx)
    cmd = {"restore": SW_RESTORE, "minimize": SW_MINIMIZE, "maximize": SW_MAXIMIZE}[a["mode"]]
    _hands_off(a)
    if m["pid"] not in ctx["pids"]:
        raise HelperError("refusing show-window: not the gate tree's window")
    u32 = _ui()["u32"]
    hw = ctx_hwnd(m["hwnd"])
    before = _fg()
    u32.ShowWindow(hw, cmd)
    time.sleep(SETTLE_S + 0.2)
    _ilog(a, "show-window", "sent", mode=a["mode"], target="tree", hwnd=m["hwnd"], pid=m["pid"])
    return {
        "mode": a["mode"],
        "iconic": bool(u32.IsIconic(hw)),
        "zoomed": bool(u32.IsZoomed(hw)),
        "frame": _frame_of(hw),
        "fg_before": before,
        "fg_after": _fg(),
    }


@_gesture("resize")
def op_resize(a: dict) -> dict:
    """Set the gate tree's main window's OUTER size (SetWindowPos, no move, no z-order,
    no activation). The live floor test needs it: a drag cannot start on the invisible
    sizing border."""
    w, h = validate_resize(a["width"], a["height"])
    ctx = _gate(a)
    m = _need_main(ctx)
    _hands_off(a)
    if m["pid"] not in ctx["pids"]:
        raise HelperError("refusing resize: not the gate tree's window")
    u32 = _ui()["u32"]
    hw = ctx_hwnd(m["hwnd"])
    before = _frame_of(hw)
    u32.SetWindowPos(
        hw, ctx_hwnd(0), 0, 0, w, h, SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE,
    )  # fmt: skip
    time.sleep(SETTLE_S + 0.2)
    _ilog(a, "resize", "sent", width=w, height=h, target="tree", hwnd=m["hwnd"], pid=m["pid"])
    rr = wintypes.RECT()
    u32.GetWindowRect(hw, ctypes.byref(rr))
    r = [rr.left, rr.top, rr.right, rr.bottom]
    return {
        "requested": {"width": w, "height": h},
        "before_frame": before,
        "outer_rect": r,
        "outer_size": [r[2] - r[0], r[3] - r[1]] if r else None,
        "frame": _frame_of(hw),
    }


@_gesture("focus-restore")
def op_focus_restore(a: dict) -> dict:
    root = a["root"]
    table = proc_table()
    text = g_read(root, _focus_file(root))
    if not text:
        raise HelperError("no focus.json: nothing was saved this session")
    saved = json.loads(text)
    pids, own_hwnds = _ours(root, table)
    _hands_off(a)
    fg = _fg()
    decision = focus_restore_decision(
        _saved_live(saved, table), saved["hwnd"], fg["hwnd"] if fg else None, _is_ours(fg, pids)
    )
    res: dict = {"decision": decision, "fg_before": fg, "nothing_in_front": fg is None}
    outcome = decision
    technique = a.get("technique") or DECIDED_TECHNIQUE
    if decision == "restore":
        ctx = _gate(a, required=False)
        res["technique"] = technique
        if technique == "own":
            r = _own_front(a, ctx, "restore-focus", {})
            res["own"] = r
        else:
            _set_foreground(saved["hwnd"], technique)
        time.sleep(SETTLE_S)
        fg2 = _fg()
        res["fg_after"] = fg2
        outcome = focus_restore_outcome(fg2["hwnd"] if fg2 else None, saved["hwnd"])
    res["outcome"] = outcome
    g_remove(root, _focus_file(root))
    _ilog(
        a,
        "focus-restore",
        "sent" if decision == "restore" else "ok",
        target="operator" if decision == "restore" else "none",
        result=outcome,
    )
    return res


def op_foreground(a: dict) -> dict:
    root = a["root"]
    table = proc_table()
    pids, own_hwnds = _ours(root, table)
    fg = _fg()
    if not fg:
        return {"foreground": None}
    ident = _proc_identity(fg["pid"])
    return {
        "foreground": {
            **fg,
            "class": _class_of(ctypes.c_void_p(fg["hwnd"])),
            "exe": ntpath.basename(ident["path"]),
            "ours": "own" if fg["hwnd"] in own_hwnds else ("tree" if fg["pid"] in pids else "no"),
        }
    }


def op_screen(a: dict) -> dict:
    u32 = _ui()["u32"]
    tray = u32.FindWindowW("Shell_TrayWnd", None)
    r = wintypes.RECT()
    tr = None
    if tray and u32.GetWindowRect(tray, ctypes.byref(r)):
        tr = [r.left, r.top, r.right, r.bottom]
    sm = _api()["u32"]
    return {
        "work_area_primary": _work_area_primary(),
        "taskbar": tr,
        "screen": [sm.GetSystemMetrics(0), sm.GetSystemMetrics(1)],
        "dpi": _dpi(),
        "cursor": list(_cursor()),
    }


def op_input_log(a: dict) -> dict:
    text = g_read(a["root"], a["root"] + "\\input.log") or ""
    out = summarize_input_log(text)
    if a.get("tail"):
        out["tail"] = text.splitlines()[-int(a["tail"]) :]
    return out


# ----------------------------- the own windows -----------------------------


@_gesture("own-window-show")
def op_own_show(a: dict) -> dict:
    root, oid = a["root"], a.get("id", "a")
    if oid not in OWN_IDS:
        raise HelperError(f"unknown own window id {oid!r}")
    table = proc_table()
    if _own_live(root, oid, table):
        raise HelperError(f"own window {oid!r} is already running: own-window close first")
    g_remove(root, own_file(root, oid))
    _hands_off(a)
    seconds = clamp_own_seconds(a.get("seconds"))
    topmost = bool(a.get("topmost"))
    work = _work_area_primary()
    at = tuple(a["at"]) if a.get("at") else None
    rect = place_own_window(work, OWN_SIZE, at)
    g_mkdirs(root, root + "\\own")
    helper = root + "\\own\\helper-win.py"
    g_write(root, helper, a["helper_source"])
    req = json.dumps(
        {
            "op": "own_main",
            "args": {
                "root": root,
                "id": oid,
                "seconds": seconds,
                "rect": rect,
                "topmost": topmost,
                "topmost_seconds": clamp_topmost_seconds(a.get("topmost_seconds")),
            },
        }
    )
    out = root + "\\own\\out-" + oid + ".txt"
    script = (
        f"src = open({helper!r}, encoding='utf-8').read()\n"
        f"g = {{'__name__': '__main__', '_WIN_REQUEST': {req!r}, '_WIN_OUT': {out!r}}}\n"
        "exec(compile(src, 'helper', 'exec'), g)\n"
    )
    wrapper = root + "\\own\\own-" + oid + ".py"
    g_write(root, wrapper, script)
    subprocess.Popen(  # noqa: S603
        [BASE_PYTHON_DIR + "\\pythonw.exe", wrapper],
        cwd=root,
        env=_scrubbed_environ(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=0x00000008 | 0x00000200,
    )
    deadline = time.time() + 15
    rec = None
    while time.time() < deadline:
        rec = _own_live(root, oid)
        if rec:
            break
        time.sleep(0.1)
    if not rec:
        raise HelperError("the own window did not publish its HWND within 15s")
    res = {
        "id": oid,
        "pid": rec["pid"],
        "hwnd": rec["hwnd"],
        "rect": _frame_of(ctx_hwnd(rec["hwnd"])),
    }
    try:
        ctx = _gate(a, required=False)
        m = _main_window(ctx) if ctx["pids"] else None
        if m:
            fb = m["frame_bounds"] or m["outer"]
            res["overlaps_tree"] = rects_intersect(res["rect"], fb)
            if res["overlaps_tree"] and a.get("no_overlap"):
                raise HelperError("the own window overlaps the test copy's window (--no-overlap)")
    except HelperError as e:
        if "overlaps" in str(e):
            raise
    _ilog(
        a,
        "own-window-show",
        "sent",
        target="own",
        hwnd=rec["hwnd"],
        pid=rec["pid"],
        id=oid,
        topmost=topmost,
    )
    return res


def _own_close_one(a: dict, oid: str, table: dict) -> dict:
    root = a["root"]
    rec = _own_live(root, oid, table)
    if not rec:
        g_remove(root, own_file(root, oid))
        return {"id": oid, "result": "not-running"}
    hw = ctx_hwnd(rec["hwnd"])
    fg = _fg()
    if fg and fg["hwnd"] == rec["hwnd"]:
        _hands_off(a)  # closing the front window moves the foreground
    _ui()["u32"].PostMessageW(hw, WM_CLOSE, 0, 0)
    deadline = time.time() + 4
    while time.time() < deadline:
        if not identity_matches(rec, proc_table().get(rec["pid"])):
            g_remove(root, own_file(root, oid))
            return {"id": oid, "result": "closed"}
        time.sleep(0.2)
    res = _kill_one(rec, _allowed_dirs(root))
    _audit(root, a.get("actor", "helper"), {**rec, "role": "own-" + oid}, res)
    g_remove(root, own_file(root, oid))
    return {"id": oid, "result": "killed:" + res}


@_gesture("own-window-close")
def op_own_close(a: dict) -> dict:
    ids = [a["id"]] if a.get("id") else list(OWN_IDS)
    table = proc_table()
    out = [_own_close_one(a, oid, table) for oid in ids]
    _ilog(a, "own-window-close", "sent", target="own", closed=out)
    return {"closed": out}


def _own_do(a: dict, oid: str, action: str, params: dict) -> dict:
    root = a["root"]
    rec = _own_live(root, oid)
    if not rec:
        raise HelperError(f"refusing own-window do: no live own window {oid!r}")
    nonce = hashlib.sha256(f"{time.time()}{os.getpid()}".encode()).hexdigest()[:12]
    cmd = make_command(action, nonce, time.time(), {**params, "run_id": a.get("run_id")})
    g_mkdirs(root, root + "\\own")
    g_write(root, own_cmd_file(root, oid), json.dumps(cmd))
    deadline = time.time() + CMD_TTL_S + 2
    rf = root + "\\own\\result-" + nonce + ".json"
    while time.time() < deadline:
        text = g_read(root, rf)
        if text:
            g_remove(root, rf)
            return json.loads(text)
        time.sleep(0.1)
    raise HelperError("the own window did not answer its command (expired?)", code=1)


@_gesture("own-window-do")
def op_own_do(a: dict) -> dict:
    ctx = _gate(a, required=False)
    oid = a.get("id", "a")
    if a["action"] not in CMD_ALLOWLIST:
        raise HelperError(
            f"refusing own-window do {a['action']!r}: not in the allowlist {CMD_ALLOWLIST}"
        )
    _hands_off(a)
    fg = _fg()
    rec = ctx["owns"].get(oid)
    res = _own_do(
        a, oid, a["action"], {"tree_id": ctx["tree_id"], "technique": a.get("technique", "sfw")}
    )
    _ilog(
        a,
        "own-window-do",
        "sent",
        target="own",
        hwnd=rec["hwnd"] if rec else None,
        pid=rec["pid"] if rec else None,
        action=a["action"],
    )
    res["fg_when_issued"] = fg
    return res


def _own_exec(root: str, cmd: dict, oid: str) -> dict:
    """Run one allowlisted command INSIDE the own window's process, re-checking
    hands-off, the gate identity and (restore-focus) the focus decision table."""
    action, params = cmd["action"], cmd.get("params") or {}
    a = {
        "root": root,
        "run_id": params.get("run_id"),
        "tree_id": params.get("tree_id"),
        "hands_off_timeout": 3,
    }
    try:
        _hands_off(a)
    except HelperError as e:
        return {"ok": False, "reason": "hands-off", "detail": str(e)}
    u32 = _ui()["u32"]
    table = proc_table()
    if action == "front-tree":
        ctx = _gate(a)
        m = _need_main(ctx)
        hw = ctx_hwnd(m["hwnd"])
        if u32.IsIconic(hw):
            u32.ShowWindow(hw, SW_RESTORE)
        if params.get("technique") == "switch":
            u32.SwitchToThisWindow(hw, True)
            sfw = None
        else:
            sfw = bool(u32.SetForegroundWindow(hw))
        time.sleep(SETTLE_S)
        fg = _fg()
        return {
            "ok": True,
            "action": action,
            "sfw_return": sfw,
            "fg_after": fg,
            "in_front": bool(fg and fg["hwnd"] == m["hwnd"]),
        }
    if action == "restore-focus":
        text = g_read(root, _focus_file(root))
        if not text:
            return {"ok": False, "reason": "no-focus-record"}
        saved = json.loads(text)
        pids, _hw = _ours(root, table)
        fg = _fg()
        decision = focus_restore_decision(
            _saved_live(saved, table), saved["hwnd"], fg["hwnd"] if fg else None, _is_ours(fg, pids)
        )
        if decision != "restore":
            return {"ok": True, "action": action, "decision": decision}
        u32.SetForegroundWindow(ctx_hwnd(saved["hwnd"]))
        time.sleep(SETTLE_S)
        fg2 = _fg()
        return {
            "ok": True,
            "action": action,
            "decision": decision,
            "fg_after": fg2,
            "outcome": focus_restore_outcome(fg2["hwnd"] if fg2 else None, saved["hwnd"]),
        }
    return {"ok": False, "reason": "not-allowed"}


def op_own_main(a: dict) -> dict:
    """The own window's process: a small stdlib window, a command-file poll, a
    lifetime limit. Shown with SW_SHOWNOACTIVATE and WS_EX_NOACTIVATE, so showing it
    never takes the foreground; a click on it asks for the foreground."""
    w = _ui()
    u32, gdi, k32 = w["u32"], w["gdi"], w["k32"]
    root, oid = a["root"], a["id"]
    rect = a["rect"]
    state = {
        "seen": set(),
        "deadline": time.time() + a["seconds"],
        "topmost_until": time.time() + a["topmost_seconds"] if a["topmost"] else None,
        "busy": False,
    }
    colour = 0x00D8B070 if oid == "a" else 0x0070B8F0  # BGR: A light blue, B light orange
    brush = gdi.CreateSolidBrush(colour)
    title = "the-one-f5 helper" + ("" if oid == "a" else " B")

    def log_event(kind: str, **kw) -> None:
        try:
            g_write(
                root,
                root + "\\own\\events-" + oid + ".log",
                json.dumps({"t": utc_now(), "kind": kind, **kw}) + "\n",
                append=True,
            )
        except Exception:  # noqa: BLE001
            pass

    def wndproc(hwnd, msg, wp, lp):
        if msg == WM_PAINT:
            ps = _PAINTSTRUCT()
            hdc = u32.BeginPaint(hwnd, ctypes.byref(ps))
            gdi.SetBkMode(hdc, 1)
            text = "helper " + oid.upper()
            gdi.TextOutW(hdc, 12, 12, text, len(text))
            u32.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        if msg == WM_LBUTTONDOWN:
            ok = bool(u32.SetForegroundWindow(hwnd))
            fg = _fg()
            log_event("click", sfw=ok, fg_is_self=bool(fg and fg["hwnd"] == int(hwnd)))
            return 0
        if msg == WM_TIMER:
            try:
                poll()
            except Exception as e:  # noqa: BLE001
                log_event("poll-error", error=f"{type(e).__name__}: {e}")
            return 0
        if msg == WM_DESTROY:
            u32.PostQuitMessage(0)
            return 0
        return u32.DefWindowProcW(hwnd, msg, wp, lp)

    cb = _WNDPROC(wndproc)

    def poll() -> None:
        if state["busy"]:
            return
        now = time.time()
        if now >= state["deadline"]:
            u32.DestroyWindow(state["hwnd"])
            return
        if state["topmost_until"] and now >= state["topmost_until"]:
            state["topmost_until"] = None
            u32.SetWindowPos(
                state["hwnd"], ctypes.c_void_p(HWND_NOTOPMOST), 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )  # fmt: skip
        cf = own_cmd_file(root, oid)
        if not os.path.isfile(local_path(cf)):
            return
        state["busy"] = True
        try:
            text = g_read(root, cf)
            g_remove(root, cf)
            try:
                cmd = json.loads(text or "")
            except ValueError:
                log_event("cmd-ignored", reason="malformed")
                return
            ok, why = validate_command(cmd, time.time(), state["seen"])
            nonce = cmd.get("nonce") if isinstance(cmd, dict) else None
            if not ok:
                log_event("cmd-ignored", reason=why, nonce=nonce)
                if isinstance(nonce, str) and nonce:
                    g_write(
                        root,
                        root + "\\own\\result-" + nonce + ".json",
                        json.dumps({"ok": False, "reason": why}),
                    )
                return
            state["seen"].add(nonce)
            res = _own_exec(root, cmd, oid)
            log_event("cmd-ran", action=cmd["action"], nonce=nonce, ok=res.get("ok"))
            g_write(root, root + "\\own\\result-" + nonce + ".json", json.dumps(res))
        finally:
            state["busy"] = False

    hinst = k32.GetModuleHandleW(None)
    cls = f"TheOneF5Own{oid}"
    wc = _WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(wc)
    wc.lpfnWndProc = cb
    wc.hInstance = hinst
    wc.hCursor = u32.LoadCursorW(None, ctypes.c_void_p(32512))
    wc.hbrBackground = brush
    wc.lpszClassName = cls
    if not u32.RegisterClassExW(ctypes.byref(wc)):
        raise HelperError("RegisterClassExW failed", code=1)
    ex = WS_EX_NOACTIVATE | (WS_EX_TOPMOST if a["topmost"] else 0)
    style = 0x00C00000 | 0x00080000  # WS_CAPTION | WS_SYSMENU
    hwnd = u32.CreateWindowExW(
        ex, cls, title, style, rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1],
        None, None, hinst, None,
    )  # fmt: skip
    if not hwnd:
        raise HelperError("CreateWindowExW failed", code=1)
    state["hwnd"] = hwnd
    u32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    u32.UpdateWindow(hwnd)
    ident = _proc_identity(os.getpid())
    rec = {
        "id": oid,
        "pid": os.getpid(),
        "create": ident["create"],
        "path": ident["path"],
        "hwnd": int(hwnd),
        "title": title,
        "started": utc_now(),
        "expires": state["deadline"],
        "topmost": a["topmost"],
    }
    g_write(root, own_file(root, oid), json.dumps(rec))
    u32.SetTimer(hwnd, 1, 50, None)
    msg = _MSG()
    while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        u32.TranslateMessage(ctypes.byref(msg))
        u32.DispatchMessageW(ctypes.byref(msg))
    text = g_read(root, own_file(root, oid))
    try:
        if text and json.loads(text).get("pid") == os.getpid():
            g_remove(root, own_file(root, oid))
    except ValueError:
        pass
    return {"closed": True}


# ----------------------------- premise 13 trials ---------------------------


@_gesture("front-trial")
def op_front_trial(a: dict) -> dict:
    """Diagnostic for premise 13: N trials of one technique from a start state. A
    start of ``a`` or ``b`` first puts that own window in front through a gated
    click; the trial then asks for the test copy's window and reads the foreground
    again after the settle time."""
    ctx = _gate(a)
    technique, start, count = a["technique"], a["start"], int(a.get("count", 5))
    if technique not in TECHNIQUES:
        raise HelperError(f"unknown technique {technique!r}")
    trials = []
    for n in range(count):
        t: dict = {"n": n + 1}
        ctx = _gate(a)
        m = _need_main(ctx)
        _hands_off(a)
        if start in OWN_IDS:
            rec = ctx["owns"].get(start)
            if not rec:
                raise HelperError(f"no live own window {start!r}")
            fr = _frame_of(ctx_hwnd(rec["hwnd"]))
            try:
                _click_core(dict(a), ctx, (fr[0] + fr[2]) // 2, (fr[1] + fr[3]) // 2 + 12, False)
            except HelperError as e:
                t["start"] = f"click-refused: {e}"
                trials.append(t)
                continue
            time.sleep(0.25)
            fg0 = _fg()
            t["start_in_front"] = bool(fg0 and fg0["hwnd"] == rec["hwnd"])
            if not t["start_in_front"]:
                t["start"] = "start-window-not-in-front"
        else:
            fg0 = _fg()
        t["fg_before"] = fg0
        t0 = time.perf_counter()
        try:
            if technique == "own":
                r = _own_front(
                    a, ctx, "front-tree", {"tree_id": ctx["tree_id"], "technique": "sfw"}
                )
                t["own"] = {k: r.get(k) for k in ("ok", "sfw_return", "in_front", "reason")}
            else:
                _set_foreground(m["hwnd"], technique)
        except HelperError as e:
            t["error"] = str(e)[:200]
        t["apply_s"] = round(time.perf_counter() - t0, 3)
        time.sleep(SETTLE_S)
        fg = _fg()
        t["fg_after"] = fg
        t["in_front"] = bool(fg and fg["hwnd"] == m["hwnd"])
        trials.append(t)
    wins = sum(1 for t in trials if t.get("in_front"))
    _ilog(
        a,
        "front-trial",
        "sent",
        target="tree",
        technique=technique,
        start=start,
        wins=wins,
        count=count,
    )
    return {"technique": technique, "start": start, "wins": wins, "count": count, "trials": trials}


_OPS = {
    "host_paths": op_host_paths,
    "operator_forms": op_operator_forms,
    "doctor_host": op_doctor_host,
    "snapshot": op_snapshot,
    "hands_off": op_hands_off,
    "launch": op_launch,
    "tree": op_tree,
    "windows": op_windows,
    "rect": op_rect,
    "stop": op_stop,
    "build_venv": op_build_venv,
    "freeze": op_freeze,
    "doctor": op_doctor,
    "net": op_net,
    "last_input": op_last_input,
    "resolve": op_resolve,
    "serve_check": op_serve_check,
    "own_show": op_own_show,
    "own_close": op_own_close,
    "own_do": op_own_do,
    "own_main": op_own_main,
    "front": op_front,
    "front_trial": op_front_trial,
    "capture": op_capture,
    "pixel": op_pixel,
    "keys": op_keys,
    "release_all": op_release_all,
    "click": op_click,
    "drag": op_drag,
    "show_window": op_show_window,
    "resize": op_resize,
    "focus_save": op_focus_save,
    "focus_restore": op_focus_restore,
    "foreground": op_foreground,
    "screen": op_screen,
    "input_log": op_input_log,
}


def _win_entry() -> None:
    req = json.loads(globals()["_WIN_REQUEST"])
    try:
        out = {"ok": True, "data": _OPS[req["op"]](req.get("args", {}))}
    except HelperError as e:
        out = {"ok": False, "error": str(e), "code": e.code}
    except Exception as e:  # noqa: BLE001
        import traceback

        out = {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "code": 1,
            "tb": traceback.format_exc(),
        }
    text = RESULT_MARK + json.dumps(out) + "\n"
    dest = globals().get("_WIN_OUT")
    if dest:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text)
    elif sys.stdout is not None:
        sys.stdout.write(text)
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# --- WSL side: the CLI
# ---------------------------------------------------------------------------


RUN_ID: str | None = None


def win_call(op: str, timeout: int | None = None, **args) -> dict:
    """Run one Windows-half op: this file's source piped to python.exe on stdin."""
    src = Path(__file__).read_text(encoding="utf-8")
    if RUN_ID and "run_id" not in args:
        args["run_id"] = RUN_ID
    prefix = "_WIN_REQUEST = " + json.dumps(json.dumps({"op": op, "args": args})) + "\n"
    proc = subprocess.run(
        [PYTHON_WIN, "-X", "utf8", "-"],
        input=(prefix + src).encode("utf-8"),
        capture_output=True,
        cwd="/mnt/c/",
        timeout=timeout,
    )
    text = proc.stdout.decode("utf-8", "replace")
    for line in text.splitlines():
        if line.startswith(RESULT_MARK):
            res = json.loads(line[len(RESULT_MARK) :])
            if res["ok"]:
                return res["data"]
            raise HelperError(res["error"], res.get("code", 2))
    raise HelperError(
        f"the Windows half returned no result (exit {proc.returncode}): "
        f"{proc.stderr.decode('utf-8', 'replace')[-800:]}",
        1,
    )


def default_root() -> str:
    return host_win_paths()["localappdata"] + "\\Temp\\the-one-f5"


_HOST: dict = {}


def host_win_paths() -> dict:
    if not _HOST:
        _HOST.update(win_call("host_paths"))
    return _HOST


def ss_busy_ports() -> list[int]:
    try:
        out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    ports = set()
    for ln in out.splitlines()[1:]:
        parts = ln.split()
        if len(parts) >= 4:
            m = re.search(r":(\d+)$", parts[3])
            if m:
                ports.add(int(m.group(1)))
    return sorted(ports)


def _pretty(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _root_arg(args) -> str:
    root = to_win_path(args.root) if args.root else default_root()
    return root


def _need_root(args) -> str:
    root = _root_arg(args)
    op = win_call("operator_forms", root=root)
    validate_root(root, host_win_paths()["localappdata"], op["forms"])
    return root


def _data_dir_arg(root: str, value: str) -> str:
    return to_win_path(value, cwd=root)


def cmd_doctor_host(args) -> int:
    root = _root_arg(args)
    info = win_call("doctor_host", root=root)
    try:
        info["networking_mode"] = subprocess.run(
            ["wslinfo", "--networking-mode"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        info["networking_mode"] = None
    _pretty(info)
    return 0


def cmd_snapshot(args) -> int:
    root = _root_arg(args)
    snap = win_call("snapshot", root=root)
    if args.out:
        Path(args.out).write_text(json.dumps(snap, indent=1))
        _pretty({"snapshot_written": args.out, **{k: snap[k] for k in ("installed", "crosscheck")}})
        return 0
    before = json.loads(Path(args.compare).read_text())
    res = compare_snapshots(before, snap)
    res["installed_after"] = snap["installed"]
    _pretty(res)
    return 0 if res["ok"] else 4


def _git_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "--deduplicate", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return sorted(f for f in out.decode("utf-8").split("\0") if f)


def cmd_setup(args) -> int:
    t0 = time.time()
    root = _need_root(args)
    lroot = local_path(root)
    sentinel = os.path.join(lroot, SENTINEL)
    if not os.path.isfile(sentinel):
        if os.path.isdir(lroot) and os.listdir(lroot):
            raise HelperError(f"refusing to adopt non-empty {root!r} with no {SENTINEL} sentinel")
        os.makedirs(lroot, exist_ok=True)
        Path(sentinel).write_text("the-one flight 5 scratch root\n")
    src_root = root + "\\src"
    manifest_path = root + "\\src-manifest.json"
    prev = json.loads(g_read(root, manifest_path) or "[]")
    files = []
    src: dict[str, tuple[int, float]] = {}
    for rel in _git_files():
        p = REPO_ROOT / rel
        if p.is_symlink() or not p.is_file():
            continue
        st = p.stat()
        src[rel] = (st.st_size, st.st_mtime)
        files.append(rel)
    dest: dict[str, tuple[int, float]] = {}
    for rel in src:
        d = os.path.join(local_path(src_root), rel.replace("/", os.sep))
        try:
            st = os.stat(d)
            dest[rel] = (st.st_size, st.st_mtime)
        except OSError:
            pass
    for rel in prev:
        d = os.path.join(local_path(src_root), rel.replace("/", os.sep))
        if rel not in dest and os.path.isfile(d):
            st = os.stat(d)
            dest[rel] = (st.st_size, st.st_mtime)
    plan = plan_sync(src, dest, prev)
    tc = time.time()
    real_root = real_win(root)
    dir_ok: set[str] = set()
    for rel in plan["copy"]:
        target = src_root + "\\" + rel.replace("/", "\\")
        parent = os.path.dirname(local_path(target))
        if parent not in dir_ok:
            guard(root, ntpath.dirname(target))
            os.makedirs(parent, exist_ok=True)
            assert_within(win_from_local(os.path.realpath(parent)), real_root)
            dir_ok.add(parent)
        tp = local_path(target)
        if os.path.islink(tp):
            raise HelperError(f"refusing to write through a symlink: {tp}")
        shutil.copy2(REPO_ROOT / rel, tp)
    for rel in plan["delete"]:
        target = src_root + "\\" + rel.replace("/", "\\")
        g_remove(root, target)
    g_write(root, manifest_path, json.dumps(files))
    copy_s = time.time() - tc
    built = win_call("build_venv", root=root, timeout=3600)
    result = {
        "root": root,
        "files_in_tree": len(files),
        "copied": len(plan["copy"]),
        "deleted": len(plan["delete"]),
        "copy_seconds": round(copy_s, 1),
        "venv": built,
        "total_seconds": round(time.time() - t0, 1),
    }
    _pretty(result)
    return 0


def cmd_freeze(args) -> int:
    root = _need_root(args)
    t0 = time.time()
    res = win_call("freeze", root=root, timeout=3600)
    res["total_seconds"] = round(time.time() - t0, 1)
    _pretty(res)
    return 0


def _launch_common(args, root: str) -> dict:
    if args.port is None:
        raise HelperError("--port is required")
    return {
        "root": root,
        "data_dir": _data_dir_arg(root, args.data_dir),
        "port": args.port,
        "cdp_port": args.cdp_port,
        "ss_busy": ss_busy_ports(),
        "frozen": bool(getattr(args, "frozen", False)),
    }


def cmd_launch(args) -> int:
    root = _need_root(args)
    common = _launch_common(args, root)
    # The Windows half refuses (ports, data dir, .env) and then waits hands-off.
    tree_id = args.tree_id or "main"
    res = win_call(
        "launch",
        timeout=400,
        tree_id=tree_id,
        tree_id_given=bool(args.tree_id),
        script=args.script,
        max_minutes=args.max_minutes,
        helper_source=Path(__file__).read_text(encoding="utf-8"),
        **common,
    )
    _pretty(res)
    return 0


def cmd_doctor(args) -> int:
    root = _need_root(args)
    if not args.data_dir:
        raise HelperError("--data-dir is required")
    res = win_call(
        "doctor",
        timeout=900,
        root=root,
        data_dir=_data_dir_arg(root, args.data_dir),
        frozen=args.frozen,
    )
    _pretty(res)
    ok = (
        res["exit_code"] == 0
        and res["result_line"] == "RESULT: PASS"
        and all(res["needles"].values())
    )
    return 0 if ok else 1


def cmd_tree(args) -> int:
    _pretty(win_call("tree", root=_need_root(args), tree_id=args.tree_id))
    return 0


def cmd_windows(args) -> int:
    _pretty(win_call("windows", root=_need_root(args), tree_id=args.tree_id))
    return 0


def cmd_rect(args) -> int:
    _pretty(win_call("rect", root=_need_root(args), tree_id=args.tree_id))
    return 0


def cmd_stop(args) -> int:
    res = win_call("stop", root=_need_root(args), tree_id=args.tree_id, timeout=300)
    _pretty(res)
    return 0 if all(t.get("complete") for t in res["stopped"]) else 1


def _xy(value: str, n: int, what: str) -> list[int]:
    try:
        parts = [int(p) for p in value.split(",")]
    except ValueError:
        parts = []
    if len(parts) != n:
        raise HelperError(f"{what} must be {n} comma-separated integers, got {value!r}")
    return parts


def _src() -> str:
    return Path(__file__).read_text(encoding="utf-8")


def cmd_own_window(args) -> int:
    root = _need_root(args)
    if args.action == "show":
        res = win_call(
            "own_show",
            timeout=120,
            root=root,
            id=args.id,
            at=_xy(args.at, 2, "--at") if args.at else None,
            topmost=args.topmost,
            topmost_seconds=args.topmost_seconds,
            seconds=args.seconds,
            no_overlap=args.no_overlap,
            tree_id=args.tree_id,
            helper_source=_src(),
        )
    elif args.action == "close":
        res = win_call("own_close", timeout=120, root=root, id=args.id)
    else:
        res = win_call(
            "own_do",
            timeout=120,
            root=root,
            id=args.id or "a",
            action=args.name,
            technique=args.technique,
            tree_id=args.tree_id,
        )
    _pretty(res)
    return 0


def cmd_front(args) -> int:
    _pretty(
        win_call(
            "front",
            timeout=180,
            root=_need_root(args),
            tree_id=args.tree_id,
            technique=args.technique,
        )
    )
    return 0


def cmd_front_trial(args) -> int:
    _pretty(
        win_call(
            "front_trial",
            timeout=900,
            root=_need_root(args),
            tree_id=args.tree_id,
            technique=args.technique,
            start=args.start,
            count=args.count,
        )
    )
    return 0


def cmd_capture(args) -> int:
    if args.window:
        mode = "window"
    elif args.own is not None:
        mode = "own"
    else:
        mode = "rect"
    res = win_call(
        "capture",
        timeout=300,
        root=_need_root(args),
        tree_id=args.tree_id,
        out=args.out,
        mode=mode,
        own_id=args.own or "a",
        rect=_xy(args.rect, 4, "--rect") if args.rect else None,
        series=args.series,
        interval_ms=args.interval_ms,
        print_window=args.print_window,
        allow_own_cover=args.allow_own_cover,
        splash=args.splash,
    )
    if res.get("file"):
        res["wsl"] = local_path(res["file"])
    _pretty(res)
    return 0


def cmd_pixel(args) -> int:
    res = win_call(
        "pixel",
        root=_need_root(args),
        tree_id=args.tree_id,
        x=args.x,
        y=args.y,
        size=args.size,
        own=args.own,
        allow_own_cover=args.allow_own_cover,
    )
    _pretty(res)
    return 0


def cmd_keys(args) -> int:
    _pretty(
        win_call("keys", timeout=300, root=_need_root(args), tree_id=args.tree_id, spec=args.spec)
    )
    return 0


def cmd_release_all(args) -> int:
    _pretty(win_call("release_all", root=_need_root(args)))
    return 0


def cmd_click(args) -> int:
    res = win_call(
        "click",
        timeout=300,
        root=_need_root(args),
        tree_id=args.tree_id,
        x=args.x,
        y=args.y,
        double=args.double,
    )
    _pretty(res)
    return 0


def cmd_drag(args) -> int:
    res = win_call(
        "drag",
        timeout=300,
        root=_need_root(args),
        tree_id=args.tree_id,
        x1=args.x1,
        y1=args.y1,
        x2=args.x2,
        y2=args.y2,
        caption=args.caption,
        steps=args.steps,
    )
    _pretty(res)
    return 0 if res.get("status") != "moved-unexpectedly" else 1


def cmd_show_window(args) -> int:
    mode = "restore" if args.restore else "minimize" if args.minimize else "maximize"
    _pretty(
        win_call("show_window", timeout=300, root=_need_root(args), tree_id=args.tree_id, mode=mode)
    )
    return 0


def cmd_resize(args) -> int:
    w, h = validate_resize(args.width, args.height)
    _pretty(
        win_call(
            "resize", timeout=300, root=_need_root(args), tree_id=args.tree_id, width=w, height=h
        )
    )
    return 0


def cmd_focus_save(args) -> int:
    _pretty(win_call("focus_save", root=_need_root(args), discard=args.discard))
    return 0


def cmd_focus_restore(args) -> int:
    res = win_call(
        "focus_restore",
        timeout=300,
        root=_need_root(args),
        tree_id=args.tree_id,
        technique=args.technique,
    )
    _pretty(res)
    return 0 if res["outcome"] in ("restored", "already-foreground", "operator-moved-on") else 1


def cmd_foreground(args) -> int:
    _pretty(win_call("foreground", root=_need_root(args)))
    return 0


def cmd_screen(args) -> int:
    _pretty(win_call("screen"))
    return 0


def cmd_hands_off(args) -> int:
    t0 = time.time()
    res = win_call("hands_off", root=_need_root(args), timeout=args.timeout)
    res["call_seconds"] = round(time.time() - t0, 2)
    _pretty(res)
    return 0


def cmd_input_log(args) -> int:
    _pretty(win_call("input_log", root=_need_root(args), tail=args.tail))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run-id", help="tag for this session's rows in input.log")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, root=True, **kw):
        sp = sub.add_parser(name, **kw)
        sp.set_defaults(fn=fn)
        if root:
            sp.add_argument(
                "--root", help="scratch root (default %%LOCALAPPDATA%%\\Temp\\the-one-f5)"
            )
        return sp

    add("doctor-host", cmd_doctor_host)
    sp = add("snapshot", cmd_snapshot)
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--out")
    g.add_argument("--compare")
    add("setup", cmd_setup)
    add("freeze", cmd_freeze)
    sp = add("doctor", cmd_doctor)
    sp.add_argument("--frozen", action="store_true")
    sp.add_argument("--data-dir")
    sp = add("launch", cmd_launch)
    sp.add_argument("--port", type=int)
    sp.add_argument("--data-dir", required=True)
    sp.add_argument("--cdp-port", type=int)
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--frozen", action="store_true")
    g.add_argument("--script")
    sp.add_argument("--max-minutes", type=int, default=30)
    sp.add_argument("--tree-id")
    for name, fn in (
        ("tree", cmd_tree),
        ("windows", cmd_windows),
        ("rect", cmd_rect),
        ("stop", cmd_stop),
    ):
        sp = add(name, fn)
        sp.add_argument("--tree-id")
    # ---- leg 1b: input, capture, own window, focus
    sp = add("own-window", cmd_own_window)
    sp.add_argument("action", choices=["show", "close", "do"])
    sp.add_argument("name", nargs="?", help="for `do`: front-tree or restore-focus")
    sp.add_argument("--id", choices=list(OWN_IDS))
    sp.add_argument("--at", help="x,y of the window's top-left (clamped into the work area)")
    sp.add_argument("--topmost", action="store_true")
    sp.add_argument("--topmost-seconds", type=int)
    sp.add_argument("--seconds", type=int, help="lifetime (default 60, at most 600)")
    sp.add_argument("--no-overlap", action="store_true")
    sp.add_argument("--technique", choices=["sfw", "switch"])
    sp.add_argument("--tree-id")
    sp = add("front", cmd_front)
    sp.add_argument("--tree-id")
    sp.add_argument("--technique", choices=list(TECHNIQUES))
    sp = add("front-trial", cmd_front_trial)
    sp.add_argument("--tree-id")
    sp.add_argument("--technique", choices=list(TECHNIQUES), required=True)
    sp.add_argument("--start", choices=["a", "b", "real"], required=True)
    sp.add_argument("--count", type=int, default=5)
    sp = add("capture", cmd_capture)
    sp.add_argument("--tree-id")
    sp.add_argument("--out", required=True, help="evidence file name (no directory)")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--window", action="store_true")
    g.add_argument("--own", nargs="?", const="a", choices=list(OWN_IDS))
    g.add_argument("--rect", help="x,y,w,h in screen pixels")
    sp.add_argument("--series", type=int)
    sp.add_argument("--interval-ms", type=float, default=20)
    sp.add_argument("--print-window", action="store_true")
    sp.add_argument("--allow-own-cover", action="store_true")
    sp.add_argument("--splash", action="store_true", help="a --series follows the splash window")
    sp = add("pixel", cmd_pixel)
    sp.add_argument("--tree-id")
    sp.add_argument("--x", type=int, required=True)
    sp.add_argument("--y", type=int, required=True)
    sp.add_argument("--size", type=int, default=9)
    sp.add_argument("--own", action="store_true", help="the point is on an own window")
    sp.add_argument("--allow-own-cover", action="store_true")
    sp = add("keys", cmd_keys)
    sp.add_argument("spec")
    sp.add_argument("--tree-id")
    add("release-all", cmd_release_all)
    sp = add("click", cmd_click)
    sp.add_argument("x", type=int)
    sp.add_argument("y", type=int)
    sp.add_argument("--double", action="store_true")
    sp.add_argument("--tree-id")
    sp = add("drag", cmd_drag)
    for n in ("x1", "y1", "x2", "y2"):
        sp.add_argument(n, type=int)
    sp.add_argument("--caption", action="store_true")
    sp.add_argument("--steps", type=int, default=12)
    sp.add_argument("--tree-id")
    sp = add("show-window", cmd_show_window)
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--restore", action="store_true")
    g.add_argument("--minimize", action="store_true")
    g.add_argument("--maximize", action="store_true")
    sp.add_argument("--tree-id")
    sp = add("resize", cmd_resize)
    sp.add_argument("--width", type=int, required=True)
    sp.add_argument("--height", type=int, required=True)
    sp.add_argument("--tree-id")
    sp = add("focus-save", cmd_focus_save)
    sp.add_argument("--discard", action="store_true")
    sp = add("focus-restore", cmd_focus_restore)
    sp.add_argument("--technique", choices=list(TECHNIQUES))
    sp.add_argument("--tree-id")
    add("foreground", cmd_foreground)
    add("screen", cmd_screen, root=False)
    sp = add("hands-off", cmd_hands_off)
    sp.add_argument("--timeout", type=int, default=HANDS_OFF_WAIT_S)
    sp = add("input-log", cmd_input_log)
    sp.add_argument("--tail", type=int)
    return p


def main(argv: list[str] | None = None) -> int:
    global RUN_ID
    args = build_parser().parse_args(argv)
    RUN_ID = args.run_id or os.environ.get("THE_ONE_F5_RUN")
    try:
        return args.fn(args)
    except HelperError as e:
        print(f"REFUSED: {e}" if e.code == 2 else f"ERROR: {e}", file=sys.stderr)
        return e.code
    except subprocess.TimeoutExpired as e:
        print(f"ERROR: timeout: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if "_WIN_REQUEST" in globals():
        _win_entry()
    else:
        sys.exit(main())
