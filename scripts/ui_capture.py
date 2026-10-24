#!/usr/bin/env python3
"""UI capture tool (Mission 31 Flight 1, DD10): before/after evidence PNGs.

Starts its OWN scratch dev instance (port 8490 or higher, a fresh data directory
under ``$HOME``, a scratch cwd, dev mode on), seeds it through the API, opens named
UI surfaces in a pinned browser environment (viewport, theme, time zone, locale,
fixed clock) in both themes and writes ``<surface>--light.png`` / ``--dark.png`` plus
``manifest.json`` to ``--out``.

The output is local flight-log evidence and is NEVER committed: ``--out`` inside the
repo is refused, and the operator approves each flight's set at the HAT.

Refusals (``check_capture_safety``): ports 8484/8485 and anything below 8490; a data
dir equal to, inside or containing the platformdirs default data dir or any
``THE_ONE_DATA_DIR`` named in the environment or the repo's ``.env``; an out dir
inside the repo.

``THE_ONE_TEST_NETNS=1`` re-runs the whole script inside a loopback-only network
namespace (``unshare -rn``, ``lo`` up) before anything starts, as
``scripts/run-tests.sh`` does: Chromium under WSL mirrored networking otherwise
aborts loopback requests with ``ERR_NETWORK_CHANGED``.

    THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out DIR
    .venv/bin/python scripts/ui_capture.py --list
    .venv/bin/python scripts/ui_capture.py --keep-running   # seed, print, leave it up

``--keep-running`` (M31 F4 L01) starts the scratch instance, seeds it with the same
realistic data the captures use, prints its URL, port, data dir, PID and credential file,
and exits WITHOUT stopping the instance (the HAT reuses that seed; stop it by the printed
PID). It is the same instance under the same safety refusals, and it never re-runs in a
network namespace (a browser outside it could not reach the server).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIN_PORT = 8490
FORBIDDEN_PORTS = {
    8484: "the operator's production instance",
    8485: "the Flight Director's preview instance",
}
NETNS_SENTINEL = "THE_ONE_UI_CAPTURE_IN_NETNS"
VIEWPORT = {"width": 1280, "height": 900}  # the first of SIZES (kept for the manifest)
# Every surface is captured at both widths (M31 F4): file names end --<theme>--<width>.
SIZES: dict[int, dict[str, int]] = {
    1280: {"width": 1280, "height": 900},
    1024: {"width": 1024, "height": 768},
}
# The scratch server's own system zone (tzlocal reads TZ), pinned so system mode is
# the same on every host. The browser zone is pinned per surface (Surface.tz).
SERVER_TZ = "America/Chicago"
# The operator zone the seed saves (zone mode); the default browser zone matches it so
# only the surfaces that mean to show the mismatch hint show it.
SEED_ZONE = "UTC"
THEMES = ("light", "dark")
FIXED_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
# The server stamps a plan token with the real clock; the capture rewrites the
# stamp so the "expires around" line is identical between runs (DD10 clock rule).
TOKEN_SET_AT = "2026-02-20T12:00:00+00:00"
TOKEN_EXPIRES_AROUND = "2027-02-20T12:00:00+00:00"
FIXED_CONSENT_URL = (
    "https://claude.ai/oauth/authorize?code=true&client_id=capture-fixed"
    "&response_type=code&state=capture-fixed-state&code_challenge=capture-fixed"
)

OLLAMA_CATALOG = {
    "models": [
        {"name": "llama3.2:1b", "size": 1321098329, "status": "ok"},
        {"name": "llama3.2:3b", "size": 2019377376, "status": "ok"},
        {"name": "nomic-embed-text", "size": 274302915, "status": "ok"},
    ]
}
# What the stubbed Ollama server reports: two installed models, one loaded.
OLLAMA_MODELS = [
    {"name": "llama3.2:1b", "size": 1321098329, "capabilities": ["completion", "tools"]},
    {"name": "llama3.2:3b", "size": 2019377376, "capabilities": ["completion"]},
    {"name": "nomic-embed-text", "size": 274302915, "capabilities": ["embedding"]},
]
OLLAMA_RUNNING = [{"name": "llama3.2:1b", "size": 1321098329, "size_vram": 1500000000}]
GENERIC_MODELS = [
    {"id": "model-one", "name": "model-one"},
    {"id": "model-two", "name": "model-two"},
]

# type -> (display name, POST body fields). Dummy keys and URLs only.
PROVIDERS: dict[str, tuple[str, dict]] = {
    "ollama": ("Capture Ollama", {"base_url": "http://127.0.0.1:11434"}),
    "openai-compatible": (
        "Capture OpenAI-compatible",
        {"base_url": "http://127.0.0.1:1234/v1", "api_key": "sk-capture-dummy"},
    ),
    "openai": ("Capture OpenAI", {"base_url": "https://api.openai.com/v1", "api_key": "sk-dummy"}),
    "anthropic": (
        "Capture Anthropic",
        {"base_url": "https://api.anthropic.com", "api_key": "sk-ant-dummy"},
    ),
    "anthropic-plan": ("Capture Claude Plan", {"base_url": "https://api.anthropic.com"}),
    "anthropic-plan-token": (
        "Capture Claude Token",
        {"base_url": "https://api.anthropic.com", "api_key": "sk-ant-oat01-capture-dummy"},
    ),
    "openrouter": (
        "Capture OpenRouter",
        {"base_url": "https://openrouter.ai/api/v1", "api_key": "sk-or-dummy"},
    ),
    "mock": (
        "Capture Mock",
        {"base_url": "http://mock.invalid", "config": {"models": ["mock-default", "mock-large"]}},
    ),
}
FLASH_PROVIDER = (
    "Capture Flash demo",
    {"base_url": "http://mock.invalid", "config": {"models": ["mock-default"]}},
)


class CaptureError(Exception):
    """A refusal or environment failure; the message goes to stderr, exit 2."""


# ── Safety ───────────────────────────────────────────────────────────────────


def _inside_or_equal(path: Path, root: Path) -> bool:
    path, root = path.resolve(), root.resolve()
    return path == root or root in path.parents


def check_capture_safety(
    port: int,
    data_dir: Path,
    out_dir: Path,
    default_dir: Path,
    env_data_dirs: list[Path],
    repo_root: Path,
) -> None:
    """Raise CaptureError when the run would touch a protected port, data
    directory or the repo. All path comparisons happen after ``resolve()``."""
    if port in FORBIDDEN_PORTS:
        raise CaptureError(f"refusing port {port}: that is {FORBIDDEN_PORTS[port]}.")
    if port < MIN_PORT:
        raise CaptureError(f"refusing port {port}: capture instances use {MIN_PORT} or higher.")
    protected = [("the default data directory", default_dir)]
    protected += [("a THE_ONE_DATA_DIR from the environment or .env", d) for d in env_data_dirs]
    for label, protected_dir in protected:
        if _inside_or_equal(data_dir, protected_dir) or _inside_or_equal(protected_dir, data_dir):
            raise CaptureError(
                f"refusing data directory {data_dir}: it is, is inside, or contains {label} "
                f"({protected_dir}). Use a scratch directory."
            )
    if _inside_or_equal(out_dir, repo_root):
        raise CaptureError(
            f"refusing --out {out_dir}: it is inside the repo ({repo_root}). Captures are "
            "local evidence and are never committed; write them outside the repo."
        )


def collect_env_data_dirs(environ: dict[str, str], repo_root: Path) -> list[Path]:
    """THE_ONE_DATA_DIR values from the environment and the repo's ``.env``, parsed
    as text (the app's settings are never imported in this process)."""
    found: list[Path] = []
    value = environ.get("THE_ONE_DATA_DIR")
    if value:
        found.append(Path(value).expanduser())
    env_file = repo_root / ".env"
    if env_file.is_file():
        for raw in env_file.read_text(errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].lstrip()
            key, sep, val = line.partition("=")
            if sep and key.strip() == "THE_ONE_DATA_DIR":
                val = val.strip().strip("'\"")
                if val:
                    found.append(Path(val).expanduser())
    return found


def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "webkitgtk_probe", REPO_ROOT / "scripts" / "webkitgtk_probe.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def default_data_dir() -> Path:
    """The platformdirs default, derived by the app itself (never a literal)."""
    probe = _load_probe()
    try:
        return probe.default_data_dir()
    except probe.ProbeError as exc:
        raise CaptureError(str(exc)) from exc


# ── Surface table ────────────────────────────────────────────────────────────


@dataclass
class Ctx:
    """What a surface's prepare step can use."""

    page: object
    base_url: str
    ids: dict[str, str]  # provider type -> id; "flash" -> flash-demo provider id
    theme: str
    token: str = ""


@dataclass
class Surface:
    name: str
    hash: str  # may contain {type} / {flash} placeholders resolved from ids
    ready: str  # CSS selector for the settled state
    description: str
    prepare: Callable[[Ctx], None] | None = None
    shot: str | None = None  # CSS selector of an element to shoot instead of the viewport
    stubs: tuple[str, ...] = ("models",)
    skipped: str | None = None
    tz: str = "UTC"  # the browser's time zone for this surface
    # Undoes server-side state the surface changed (called with base, token, ids after
    # EVERY theme/width capture, so the next one starts clean).
    restore: Callable[[str, str, dict[str, str]], None] | None = None


def _ollama_stubs(page) -> None:
    page.route(
        "**/api/providers/*/models",
        lambda r: r.fulfill(json=OLLAMA_MODELS) if r.request.method == "GET" else r.continue_(),
    )
    page.route("**/api/providers/*/models/status", lambda r: r.fulfill(json=OLLAMA_RUNNING))


def _stub_test(status: str, detail: str):
    def prepare(ctx: Ctx) -> None:
        ctx.page.route(
            "**/api/providers/*/test",
            lambda r: r.fulfill(json={"status": status, "detail": detail}),
        )
        ctx.page.locator('[data-testid="test-connection-btn"]').click()
        result = ctx.page.locator(
            '[data-testid="provider-test-result"]:not([data-state="pending"])'
        )
        result.wait_for(timeout=10000)
        result.scroll_into_view_if_needed()

    return prepare


def _plan_awaiting_code(ctx: Ctx) -> None:
    page = ctx.page
    page.locator('[data-testid="plan-signin-btn"]').click()
    page.locator('[data-testid="plan-signin-consent"]').wait_for(timeout=10000)
    # The authorize URL carries a random state and challenge; pin it.
    page.evaluate(
        "u => { const i = document.querySelector('[data-testid=\"plan-signin-url\"]');"
        " if (i) i.value = u; }",
        FIXED_CONSENT_URL,
    )
    for extra in page.context.pages:  # the aborted claude.ai popup, if one opened
        if extra is not page:
            extra.close()


def _stub_mcp_tools(page) -> None:
    page.route(
        "**/api/mcp-sources/*/test/connect",
        lambda r: r.fulfill(
            json={
                "status": "ok",
                "tools": [{"name": n, "description": d} for n, d in CAPTURE_MCP_TOOLS],
            }
        ),
    )


def _mcps_expanded(ctx: Ctx) -> None:
    _stub_mcp_tools(ctx.page)
    ctx.page.locator(f'[data-testid="mcp-source-expand-{ctx.ids["mcpsrc"]}"]').click()
    ctx.page.locator('[data-testid^="mcp-tool-toggle-"]').first.wait_for(timeout=10000)


def _tools_override_open(ctx: Ctx) -> None:
    page = ctx.page
    tile = page.locator('.ui-group-tile[data-category="Filesystem"]')
    tile.locator(".ui-group-tile-expand").click()
    panel = page.locator('details.ui-tool-row[data-tool="read_file"]')
    panel.locator(".ui-tool-row-affordance").click()
    panel.locator(
        '.chip-list-editor[data-tool-override-field="path_denylist"] .chip'
    ).first.wait_for(timeout=10000)
    panel.scroll_into_view_if_needed()


def _admin_tool_chips(ctx: Ctx) -> None:
    ctx.page.locator(".chip-list-editor .chip").first.wait_for(timeout=10000)


def _flash_after_save(ctx: Ctx) -> None:
    page = ctx.page
    page.locator("#pf-name").fill("Capture Flash demo (edited)")
    save = page.locator('[data-testid="save-provider-btn"]')
    save.click()
    page.locator(".app-flash.visible").wait_for(timeout=10000)


# ── Library surfaces (Mission 31 Flight 3, DD2) ──────────────────────────────

# MASK RULE (M31 F4 L01): a run-to-run value is replaced by a FIXED value of the SAME
# SHAPE, never by a label. A timestamp stays a timestamp in its real format (an ISO
# string stays an ISO string, a "Mar 1, 3:04 PM" stays that form), a duration keeps its
# unit, a score keeps its digit count, a pairing code keeps its length and character
# class. Replacing a whole element's text with a label ("Indexed (time masked)") hid the
# exact text the operator later objected to (Flight 3 debrief). Matching is done per text
# node inside known containers, so child structure is untouched; the observer re-applies
# the masks after a poll repaints. The run id inside the scratch folder path is pinned.
MASK_JS = r"""
() => {
  const MON = '(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)';
  const TIME_RULES = [
    [/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?/g,
      (m, frac, zone) => '2026-03-01T12:00:00' + (frac ? '.' + '0'.repeat(frac.length - 1) : '')
        + (zone || '')],
    [/\b(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day, [A-Z][a-z]+ \d{1,2}, \d{4}/g,
      () => 'Sunday, March 1, 2026'],
    [/\d{4}-\d{2}-\d{2}(?!T)/g, () => '2026-03-01'],
    [new RegExp('\\b(' + MON + ') \\d{1,2}(, \\d{4})?', 'g'),
      (m, mon, yr) => 'Mar 1' + (yr ? ', 2026' : '')],
    [/(?<![\dT+:-])\b\d{1,2}:\d{2}(:\d{2})?( ?[AP]M)?/g,
      // The meridiem is pinned too ("PM", the spacing kept): the real one flips with the
      // time of day the capture runs, which read as a difference between two runs.
      (m, sec, ap) => '12:00' + (sec ? ':00' : '') + (ap ? (/^ /.test(ap) ? ' ' : '') + 'PM' : '')],
    [/\b\d+(\.\d+)?( ?ms)\b/g,
      (m, frac, unit) => (frac ? '120.5' : '120') + unit],
  ];
  const DIGITS = [/\d/g, () => '0'];
  const TIME = [
    '.kb-item-indexed-at', '.kb-folder-indexed-at', '[data-testid="kb-item-indexed-at"]',
    '.connector-pairing-expiry', '[data-testid="connector-pairing-expiry"]',
    '[data-testid^="date-time-preview"]', '[data-testid="date-time-status"]',
  ].join(', ');
  const SCORE = '.kb-search-hit-score, [data-testid="kb-search-hit-score"]';
  const CODE = '[data-testid="connector-pairing-code"]';
  const HEX = '0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d';
  // The run id sits in the scratch folder path: pin everything up to library-docs.
  const PATHS = '.kb-folder-path, [data-testid="kb-folder-path"], '
    + '.kb-search-hit-path, [data-testid="kb-search-hit-path"], '
    + '[data-testid="kb-panel-file-path"], .kb-item-path, [data-testid="kb-item-path"], '
    + '[data-testid="kb-item-full-path"]';
  const maskText = (str, rules) => {
    let out = str;
    for (const [re, fn] of rules) out = out.replace(re, fn);
    return out;
  };
  const eachText = (sel, rules) => {
    document.querySelectorAll(sel).forEach((n) => {
      if (n.tagName === 'INPUT') {
        const v = maskText(n.value, rules);
        if (v !== n.value) n.value = v;
        return;
      }
      const w = document.createTreeWalker(n, NodeFilter.SHOW_TEXT);
      let t;
      while ((t = w.nextNode())) {
        const v = maskText(t.nodeValue, rules);
        if (v !== t.nodeValue) t.nodeValue = v;
      }
    });
  };
  const apply = () => {
    document.querySelectorAll(PATHS).forEach((n) => {
      const t = n.textContent.replace(
        new RegExp('/[^ ]*?/library-docs'), '/home/capture/home/library-docs');
      if (t !== n.textContent) n.textContent = t;
    });
    eachText(TIME, TIME_RULES);
    eachText(SCORE, [DIGITS]);
    // The derived tool name carries the knowledge base's random 8-hex id.
    eachText('[data-testid^="agent-knowledge-row-"]',
      [[/(?<=_)[0-9a-f]{8}(?=__)/g, () => '1e6d8d9b']]);
    eachText(CODE, [[new RegExp('[0-9a-f]+', 'g'), (m) => HEX.slice(0, m.length)]]);
  };
  if (window.__captureMask) window.__captureMask.disconnect();
  window.__captureMask = new MutationObserver(apply);
  window.__captureMask.observe(
    document.body, {childList: true, subtree: true, characterData: true});
  apply();
}
"""

LIBRARY_FILES = {
    "harbour-notes.txt": (
        "The harbour pelican keeps the ledger of tides.\nTides rise twice a day.\n"
    ),
    "orchard.txt": "Orchard rows are numbered from the east gate.\nPick apples before the frost.\n",
    "recipes.md": "# Recipes\n\nBread needs flour, water and time.\nSoup needs patience.\n",
    "sub/readme.txt": "A nested file, so the folder lists a relative path.\n",
}
LIBRARY_QUERY = "pelican"


# Capture-only stylesheet (never product CSS): a blinking caret, a fading overlay scrollbar
# and any transition or animation make two captures of the same page differ by a few pixels.
DETERMINISM_CSS = (
    "*, *::before, *::after { caret-color: transparent !important; "
    "transition: none !important; animation: none !important; "
    "scrollbar-width: none !important; } "
    "*::-webkit-scrollbar { display: none !important; }"
)
# Software raster with grayscale text: GPU/LCD raster rounding made rounded-corner and text
# edges differ by a pixel level or two between runs.
CHROMIUM_DETERMINISM_ARGS = [
    "--disable-gpu",
    "--disable-lcd-text",
    "--font-render-hinting=none",
    "--disable-font-subpixel-positioning",
    "--force-color-profile=srgb",
    "--num-raster-threads=1",
    "--disable-partial-raster",
]
DETERMINISM_JS = (
    "(function () { function add() { if (document.getElementById('capture-determinism')) return; "
    "var s = document.createElement('style'); s.id = 'capture-determinism'; "
    "s.textContent = %s; (document.head || document.documentElement).appendChild(s); } "
    "try { add(); } catch (e) {} "
    "document.addEventListener('DOMContentLoaded', add); })();" % json.dumps(DETERMINISM_CSS)
)


def _mask(page) -> None:
    page.evaluate(MASK_JS)


def _kb_ready(ctx: Ctx) -> None:
    page = ctx.page
    _mask(page)
    page.locator('[data-testid="kb-status-count"][data-status="indexed"]').wait_for(timeout=30000)


def _kb_expand(ctx: Ctx) -> None:
    page = ctx.page
    _kb_ready(ctx)
    folder = page.locator('[data-testid="kb-folder-panel"]')
    folder.locator('[data-testid="kb-folder-summary"]').click()
    page.locator('[data-testid="kb-item-row"]').first.wait_for(state="visible", timeout=15000)
    _mask(page)


def _kb_item_menu(ctx: Ctx) -> None:
    _kb_expand(ctx)
    row = ctx.page.locator('[data-testid="kb-item-row"]').first
    row.locator('[data-testid="kb-item-menu-btn"]').click()
    row.locator('[data-testid="kb-item-menu"]').wait_for(state="visible", timeout=5000)


def _kb_chunks(ctx: Ctx) -> None:
    _kb_item_menu(ctx)
    ctx.page.locator('[data-testid="kb-item-chunks-btn"]').first.click()
    ctx.page.locator('[data-testid="kb-chunk-row"]').first.wait_for(timeout=15000)
    _mask(ctx.page)


def _kb_source(ctx: Ctx) -> None:
    _kb_item_menu(ctx)
    ctx.page.locator('[data-testid="kb-item-source-btn"]').first.click()
    ctx.page.locator('[data-testid="kb-source-text"]').wait_for(state="visible", timeout=15000)
    _mask(ctx.page)


def _kb_search(ctx: Ctx) -> None:
    page = ctx.page
    _kb_ready(ctx)
    page.locator('[data-testid="kb-search-input"]').fill(LIBRARY_QUERY)
    page.locator('[data-testid="kb-search-btn"]').click()
    page.locator('[data-testid="kb-search-hit"]').first.wait_for(timeout=20000)
    _mask(page)
    page.locator('[data-testid="kb-search-hit"]').first.scroll_into_view_if_needed()


def _kb_status(ctx: Ctx) -> None:
    page = ctx.page
    _kb_ready(ctx)
    page.locator('[data-testid="kb-reindex-all-btn"]').click()
    # Wait through the re-index on the API, then for the page's own poll to repaint.
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        st = _api(ctx.base_url, ctx.token, "GET", f"/api/knowledge-bases/{ctx.ids['kbl']}/status")
        if st["indexer"] == "idle" and st["items"].get("indexed") == len(LIBRARY_FILES):
            break
        time.sleep(0.5)
    else:
        raise CaptureError(f"kb-status: re-index did not settle: {st}")
    page.get_by_test_id("kb-indexer-state").filter(has_text="idle").wait_for(timeout=15000)
    _mask(page)
    page.locator('[data-testid="kb-status-summary"]').scroll_into_view_if_needed()


def _kb_danger_armed(ctx: Ctx) -> None:
    page = ctx.page
    _kb_ready(ctx)
    btn = page.locator(".danger-zone .delete-btn").first
    btn.scroll_into_view_if_needed()
    btn.click()
    page.locator(".danger-zone .confirm-delete").first.wait_for(timeout=5000)


def _connector_new(ctx: Ctx) -> None:
    page = ctx.page
    page.locator('select[data-field="type"]').select_option("stub")
    page.locator('input[data-field="name"]').fill("Capture stub connector")


def _connector_edit(ctx: Ctx) -> None:
    page = ctx.page
    page.locator('[data-testid="connector-doctor-btn"]').click()
    page.locator('[data-testid="connector-doctor-result"]:not(:empty)').wait_for(timeout=15000)
    page.locator('[data-testid="connector-pairing-btn"]').click()
    page.locator('[data-testid="connector-pairing-code"]').wait_for(timeout=15000)
    _mask(page)
    page.locator('[data-testid="connector-pairing-result"]').scroll_into_view_if_needed()


# ── Settings surfaces (Mission 31 Flight 4, DD2) ─────────────────────────────

READ_FILE_ALLOWLIST = (
    "/home/capture/workspaces/project-archive/documentation/reference"
    "/yearly/2026/quarter-one/drafts/a"
)
assert len(READ_FILE_ALLOWLIST) == 97
READ_FILE_SIZE_CAP = 262_144  # "256KB", not the 1MB default
# Disabled globally in the seed so the Built-in tools grid shows off tiles.
GLOBALLY_DISABLED_TOOLS = ("grep", "python_exec")
SEED_KNOWLEDGE_SETTINGS = {
    "chunking": {"size_chars": 1800, "overlap_chars": 300},
    "monitoring": {"watch_enabled": False, "reconcile_interval_seconds": 900},
}
# The stubbed Test results (a real fetch cannot succeed under netns). Durations are
# fixed; the page prints them as "(142 ms)".
STUB_TEST_REFUSED = {
    "output": "[error] [constraint] host 'example.com' is not in the fetch allowlist",
    "elapsed_ms": 3.0,
    "outcome": "blocked",
}
STUB_TEST_OK = {
    "output": "<!doctype html><html><head><title>Example Domain</title></head>"
    "<body><h1>Example Domain</h1><p>This domain is for use in documentation.</p>"
    "</body></html>",
    "elapsed_ms": 142.0,
    "outcome": "ok",
}


def _put_time_settings(base: str, token: str, mode: str, zone: str | None = SEED_ZONE) -> None:
    _api(base, token, "PUT", "/api/time-settings", {"mode": mode, "zone": zone})


def _restore_zone_mode(base: str, token: str, ids: dict[str, str]) -> None:
    _put_time_settings(base, token, "zone")


def _restore_knowledge_settings(base: str, token: str, ids: dict[str, str]) -> None:
    _api(base, token, "PUT", "/api/knowledge-settings", SEED_KNOWLEDGE_SETTINGS)


def _datetime_system(ctx: Ctx) -> None:
    _put_time_settings(ctx.base_url, ctx.token, "system")
    ctx.page.reload()
    ctx.page.locator('[data-testid="date-time-mode-system"]').wait_for(timeout=15000)
    ctx.page.locator('[data-testid="date-time-preview-clock"]:not(:empty)').wait_for(timeout=15000)
    _mask(ctx.page)


def _datetime_ready(ctx: Ctx) -> None:
    ctx.page.locator('[data-testid="date-time-zone-row"]').first.wait_for(timeout=15000)
    ctx.page.locator('[data-testid="date-time-preview-clock"]:not(:empty)').wait_for(timeout=15000)
    _mask(ctx.page)


def _datetime_search(ctx: Ctx) -> None:
    page = ctx.page
    _datetime_ready(ctx)
    page.locator('[data-testid="date-time-search"]').fill("ber")
    page.wait_for_timeout(600)
    page.locator('[data-testid="date-time-zone-row"]').first.wait_for(timeout=10000)
    _mask(page)


def _prompts_ready(ctx: Ctx) -> None:
    page = ctx.page
    page.wait_for_function(
        "() => { const e = document.querySelector('[data-testid=\"date-prompt-content\"]');"
        " return e && e.textContent.trim() && !/loading|failed/i.test(e.textContent); }",
        timeout=15000,
    )
    page.locator('[data-testid^="platform-section-"]').first.wait_for(timeout=15000)


def _encryption_armed(ctx: Ctx) -> None:
    ctx.page.locator('[data-testid="rotate-key-btn"]').click()
    ctx.page.locator('[data-testid="rotate-key-btn"].confirm-delete').wait_for(timeout=5000)


def _encryption_staged(ctx: Ctx) -> None:
    page = ctx.page
    # The real rotation re-encrypts every stored secret: never run it. Stub the route.
    page.route(
        "**/api/encryption/rotate",
        lambda r: r.fulfill(
            json={"status": "rotated", "key_file": "staged", "providers": "8"},
        ),
    )
    btn = page.locator('[data-testid="rotate-key-btn"]')
    btn.click()
    page.locator('[data-testid="rotate-key-btn"].confirm-delete').wait_for(timeout=5000)
    btn.click()
    page.locator('[data-testid="rotate-result"][data-state="warning"]').wait_for(timeout=10000)


def _tools_tab(tab: str):
    def prepare(ctx: Ctx) -> None:
        ctx.page.locator(f'[data-testid="tab-{tab}"]').click()
        ctx.page.locator(f'#tools-panel-{tab} [data-testid="tool-card"]').first.wait_for(
            state="visible", timeout=10000
        )

    return prepare


def _tool_editor_ready(ctx: Ctx) -> None:
    ctx.page.locator('[data-testid="save-tool-btn"]').wait_for(timeout=15000)
    ctx.page.wait_for_timeout(300)


def _tool_read_file(ctx: Ctx) -> None:
    _admin_tool_chips(ctx)


def _tool_fetch_url_error(ctx: Ctx) -> None:
    page = ctx.page
    page.locator('[data-field="redirect_cap"]').fill("-3")
    page.locator('[data-testid="save-tool-btn"]').click()
    page.locator(
        '[data-field="redirect_cap"][aria-invalid="true"], '
        ".tools-editor-field .field-error:not([hidden])"
    ).first.wait_for(timeout=10000)


def _tool_test(payload: dict):
    def prepare(ctx: Ctx) -> None:
        page = ctx.page
        page.route(
            "**/api/tools/configs/fetch_url/test",
            lambda r: r.fulfill(json=payload),
        )
        page.locator('[data-testid="test-tool-btn"]').click()
        page.locator(
            '[data-testid="test-result"][data-state="success"], '
            '[data-testid="test-result"][data-state="warning"], '
            ".test-result .test-result-ok, .test-result .test-result-fail"
        ).first.wait_for(timeout=10000)
        page.locator('[data-testid="test-tool-btn"]').scroll_into_view_if_needed()

    return prepare


def _tool_web_search_searxng(ctx: Ctx) -> None:
    page = ctx.page
    page.locator('[data-field="search_backend"]').select_option("searxng")
    page.locator('[data-field="searxng_base_url"]').wait_for(state="visible", timeout=5000)


def _knowledge_ready(ctx: Ctx) -> None:
    ctx.page.wait_for_function(
        "() => { const i = document.querySelector('#ks-size-chars'); return i && i.value !== ''; }",
        timeout=15000,
    )


def _knowledge_invalid(ctx: Ctx) -> None:
    page = ctx.page
    _knowledge_ready(ctx)
    page.locator("#ks-size-chars").fill("50")
    page.locator("#ks-overlap-chars").fill("5000")
    page.locator("#ks-reconcile-interval").fill("2")
    page.locator("#ks-reconcile-interval").press("Tab")
    page.locator('[data-testid="knowledge-size-chars-error"]:not([hidden])').wait_for(timeout=5000)


def _knowledge_saved(ctx: Ctx) -> None:
    page = ctx.page
    _knowledge_ready(ctx)
    page.locator("#ks-size-chars").fill("2000")
    page.locator("#ks-overlap-chars").fill("200")
    page.locator("#ks-reconcile-interval").fill("600")
    page.locator('[data-testid="knowledge-settings-save-btn"]').click()
    page.locator('[data-testid="knowledge-settings-flash"]:not(:empty)').wait_for(timeout=10000)


SURFACES: list[Surface] = []
for _type in PROVIDERS:
    SURFACES.append(
        Surface(
            name=f"provider-edit-{_type}",
            hash=f"#library/providers/{{{_type}}}",
            ready='[data-testid="save-provider-btn"]',
            description=f"Provider editor, edit mode, {_type}",
            stubs=("ollama",) if _type == "ollama" else ("models",),
        )
    )
SURFACES += [
    Surface(
        "provider-create",
        "#library/providers/~new",
        '[data-testid="save-provider-btn"]',
        "Provider editor, create mode",
    ),
    Surface(
        "ollama-models-panel",
        "#library/providers/{ollama}",
        ".admin-pf-model-row",
        "Ollama models panel: one loaded, two available, stubbed",
        shot=".provider-models",
        stubs=("ollama",),
    ),
    Surface(
        "provider-test-ok",
        "#library/providers/{openai-compatible}",
        '[data-testid="test-connection-btn"]',
        "Provider Test result, ok (stubbed)",
        prepare=_stub_test("ok", "Connected: 2 models available"),
    ),
    Surface(
        "provider-test-failed",
        "#library/providers/{openai-compatible}",
        '[data-testid="test-connection-btn"]',
        "Provider Test result, failed (stubbed)",
        prepare=_stub_test("error", "Connection refused: http://127.0.0.1:1234/v1"),
    ),
    Surface(
        "plan-signin-awaiting-code",
        "#library/providers/{anthropic-plan}",
        '[data-testid="plan-signin-btn"]',
        "Claude Plan (OAuth) sign-in block, awaiting the pasted code",
        prepare=_plan_awaiting_code,
        shot=".admin-pf-plan-signin",
    ),
    Surface(
        "plan-token-expiry",
        "#library/providers/{anthropic-plan-token}",
        '[data-testid="provider-token-expiry"]',
        "Claude Plan (Token) editor with the 'expires around' line (stamp and clock pinned)",
    ),
    Surface(
        "flash-after-save",
        "#library/providers/{flash}",
        '[data-testid="save-provider-btn"]',
        "The flash shown after a Save",
        prepare=_flash_after_save,
    ),
    Surface(
        "agent-general",
        "#agents/{agent}/general",
        '[data-testid="tab-general"][aria-selected="true"]',
        "Agent editor, General tab (description, system prompt filled)",
    ),
    Surface(
        "agent-rules-and-notes",
        "#agents/{agent}/rules-and-notes",
        '[data-testid="rules-row"]',
        "Agent editor, Rules and notes tab: two rules (one off), notes on, no notes",
    ),
    Surface(
        "agent-knowledge",
        "#agents/{agent}/knowledge",
        '[data-testid^="agent-knowledge-row-"]',
        "Agent editor, Knowledge tab: one knowledge base attached",
    ),
    Surface(
        "agent-mcps",
        "#agents/{agent}/mcps",
        '[data-testid^="mcp-source-expand-"]',
        "Agent editor, MCPs tab: the source expanded, four tools (stubbed)",
        prepare=_mcps_expanded,
    ),
    Surface(
        "agent-tools",
        "#agents/{agent}/tools",
        '.ui-group-tile[data-category="Filesystem"]',
        "Agent editor, Built-in Tools tab: Filesystem expanded, read_file Overrides open",
        prepare=_tools_override_open,
    ),
    Surface(
        "agent-self-configuration",
        "#agents/{agent}/self-configuration",
        '[data-testid="self-configuration-toggle-btn"]',
        "Agent editor, Self-configuration tab, enabled (no pending revision)",
    ),
    Surface(
        "agent-self-configuration-pending",
        "",
        "",
        "Self-configuration tab with a pending revision",
        skipped="a pending revision needs the agent to act (no operator API path creates one)",
    ),
    Surface(
        "agent-rules-and-notes-with-note",
        "",
        "",
        "Rules and notes tab with a kept note",
        skipped="notes are written only by the agent (no create route); seeding needs direct SQL",
    ),
    Surface(
        "admin-builtin-tool-editor",
        "#settings/tools/read_file",
        ".chip-list-editor",
        "Settings > Built-in tools, read_file editor (shared chip-list rules guard)",
        prepare=_admin_tool_chips,
    ),
    Surface(
        "library-start",
        "#library",
        '[data-testid="library-start"]',
        "Library start page: one card per type",
    ),
    Surface(
        "kb-new",
        "#library/knowledge/~new",
        '[data-testid="kb-create-name-input"]',
        "Knowledge base create form",
    ),
    Surface(
        "kb-detail",
        "#library/knowledge/{kbl}",
        '[data-testid="kb-folder-panel"]',
        "Knowledge base detail: folder expanded with its files",
        prepare=_kb_expand,
    ),
    Surface(
        "kb-item-menu",
        "#library/knowledge/{kbl}",
        '[data-testid="kb-folder-panel"]',
        "Knowledge base detail: an item's action menu open",
        prepare=_kb_item_menu,
    ),
    Surface(
        "kb-chunks",
        "#library/knowledge/{kbl}",
        '[data-testid="kb-folder-panel"]',
        "Knowledge base detail: the chunks panel of one item",
        prepare=_kb_chunks,
    ),
    Surface(
        "kb-source",
        "#library/knowledge/{kbl}",
        '[data-testid="kb-folder-panel"]',
        "Knowledge base detail: the extracted-source panel of one item",
        prepare=_kb_source,
    ),
    Surface(
        "kb-search",
        "#library/knowledge/{kbl}",
        '[data-testid="kb-folder-panel"]',
        "Knowledge base detail: search preview with hits (scores masked)",
        prepare=_kb_search,
    ),
    Surface(
        "kb-status",
        "#library/knowledge/{kbl}",
        '[data-testid="kb-folder-panel"]',
        "Knowledge base detail: status section after a full re-index",
        prepare=_kb_status,
    ),
    Surface(
        "kb-danger-armed",
        "#library/knowledge/{kbl}",
        '[data-testid="kb-folder-panel"]',
        "Knowledge base detail: the Danger Zone delete armed (first click)",
        prepare=_kb_danger_armed,
    ),
    Surface(
        "connector-new",
        "#library/connectors/~new",
        '[data-testid="connector-status-row"], select[data-field="type"]',
        "Connector create form, stub type chosen",
        prepare=_connector_new,
    ),
    Surface(
        "connector-edit",
        "#library/connectors/{conn}",
        '[data-testid="connector-doctor-btn"]',
        "Connector editor: doctor result, pairing code and two channel-map rows",
        prepare=_connector_edit,
    ),
    Surface(
        "chat-consent-link",
        "",
        "",
        "The sign-in consent link in a chat",
        skipped="leg 05's change is click feedback, which a static capture does not show",
    ),
    Surface(
        "mcp-consent-link",
        "",
        "",
        "The sign-in consent link in the MCP editor",
        skipped="leg 05's change is click feedback, which a static capture does not show",
    ),
]


def _settings(name, hash_, ready, description, **kw) -> Surface:
    return Surface(name, hash_, ready, description, **kw)


SURFACES += [
    _settings(
        "settings-appearance",
        "#settings/appearance",
        '[data-testid="theme-picker"]',
        "Settings > Appearance",
    ),
    _settings(
        "settings-datetime-system",
        "#settings/date-and-time",
        '[data-testid="date-time-mode-system"]',
        "Date and time, system mode (browser zone = server system zone)",
        prepare=_datetime_system,
        tz=SERVER_TZ,
        restore=_restore_zone_mode,
    ),
    _settings(
        "settings-datetime-zone",
        "#settings/date-and-time",
        '[data-testid="date-time-zone-row"]',
        "Date and time, zone mode with the zone list showing",
        prepare=_datetime_ready,
    ),
    _settings(
        "settings-datetime-search",
        "#settings/date-and-time",
        '[data-testid="date-time-search"]',
        "Date and time, a search with results",
        prepare=_datetime_search,
    ),
    _settings(
        "settings-datetime-mismatch",
        "#settings/date-and-time",
        '[data-testid="date-time-mismatch"]:not([hidden])',
        "Date and time, the mismatch hint (browser zone differs from the effective zone)",
        prepare=_datetime_ready,
        tz="Europe/Paris",
    ),
    _settings(
        "settings-prompts",
        "#settings/prompts",
        '[data-testid="platform-sections"]',
        "Settings > Prompts, full page",
        prepare=_prompts_ready,
    ),
    _settings(
        "settings-encryption",
        "#settings/encryption",
        '[data-testid="rotate-key-btn"]',
        "Settings > Encryption, default",
    ),
    _settings(
        "settings-encryption-armed",
        "#settings/encryption",
        '[data-testid="rotate-key-btn"]',
        "Settings > Encryption, Rotate armed (first click)",
        prepare=_encryption_armed,
    ),
    _settings(
        "settings-encryption-staged",
        "#settings/encryption",
        '[data-testid="rotate-key-btn"]',
        "Settings > Encryption, the staged-key warning (rotation route stubbed)",
        prepare=_encryption_staged,
    ),
    _settings(
        "settings-tools-filesystem",
        "#settings/tools",
        '[data-testid="tab-filesystem"]',
        "Built-in tools grid, Filesystem tab (grep disabled globally)",
        prepare=_tools_tab("filesystem"),
    ),
    _settings(
        "settings-tools-execution",
        "#settings/tools",
        '[data-testid="tab-execution"]',
        "Built-in tools grid, Execution tab (python_exec disabled globally)",
        prepare=_tools_tab("execution"),
    ),
    _settings(
        "settings-tool-read-file",
        "#settings/tools/read_file",
        ".chip-list-editor .chip",
        "read_file editor: 97-character allowlist path, 256KB read size, default denylist",
        prepare=_tool_editor_ready,
    ),
    _settings(
        "settings-tool-delete-file",
        "#settings/tools/delete_file",
        '[data-testid="save-tool-btn"]',
        "delete_file editor (the shared Filesystem fields)",
        prepare=_tool_editor_ready,
    ),
    _settings(
        "settings-tool-shell",
        "#settings/tools/shell",
        '[data-testid="save-tool-btn"]',
        "shell editor",
        prepare=_tool_editor_ready,
    ),
    _settings(
        "settings-tool-fetch-url-error",
        "#settings/tools/fetch_url",
        '[data-field="redirect_cap"]',
        "fetch_url editor with a validation error showing (redirect cap -3)",
        prepare=_tool_fetch_url_error,
    ),
    _settings(
        "settings-tool-fetch-url-refused",
        "#settings/tools/fetch_url",
        '[data-testid="test-tool-btn"]',
        "fetch_url, Test connection refused (stubbed)",
        prepare=_tool_test(STUB_TEST_REFUSED),
    ),
    _settings(
        "settings-tool-fetch-url-ok",
        "#settings/tools/fetch_url",
        '[data-testid="test-tool-btn"]',
        "fetch_url, Test connection ok (stubbed)",
        prepare=_tool_test(STUB_TEST_OK),
    ),
    _settings(
        "settings-tool-web-search",
        "#settings/tools/web_search",
        '[data-field="search_backend"]',
        "web_search with SearXNG selected (the show_if reveal)",
        prepare=_tool_web_search_searxng,
    ),
    _settings(
        "settings-tool-current-time",
        "#settings/tools/current_time",
        '[data-testid="editor-breadcrumb-link"]',
        "current_time editor (no configuration)",
    ),
    _settings(
        "settings-knowledge-default",
        "#settings/knowledge-indexing",
        "#ks-size-chars",
        "Knowledge indexing, seeded non-default values",
        prepare=_knowledge_ready,
    ),
    _settings(
        "settings-knowledge-invalid",
        "#settings/knowledge-indexing",
        "#ks-size-chars",
        "Knowledge indexing, field errors showing",
        prepare=_knowledge_invalid,
    ),
    _settings(
        "settings-knowledge-saved",
        "#settings/knowledge-indexing",
        "#ks-size-chars",
        "Knowledge indexing, after a Save",
        prepare=_knowledge_saved,
        restore=_restore_knowledge_settings,
    ),
]


def print_table() -> None:
    for s in SURFACES:
        tail = f"  SKIPPED: {s.skipped}" if s.skipped else ""
        print(f"{s.name:34} {s.hash or '-':44} {s.description}{tail}")


# ── Instance ─────────────────────────────────────────────────────────────────


def pick_port() -> int:
    for _ in range(200):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port >= MIN_PORT and port not in FORBIDDEN_PORTS:
            return port
    raise CaptureError("could not find a free port of 8490 or higher")


def write_credential(data_dir: Path) -> str:
    """The long-lived local-API credential, written before the server starts
    (same sequence as tests/browser/conftest.py::_write_credential)."""
    token = f"loc_{secrets.token_hex(8)}.{secrets.token_hex(32)}"
    path = data_dir / "api-credential"
    tmp = path.with_name(f"{path.name}.tmp.{secrets.token_hex(4)}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, token.encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    return token


def _api(base: str, token: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - loopback
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise CaptureError(f"{method} {path} -> {exc.code}: {exc.read()[:300]!r}") from exc


def start_instance(port: int, data_dir: Path, cwd: Path, log: Path, detach: bool = False):
    data_dir.mkdir(parents=True)
    cwd.mkdir(parents=True, exist_ok=True)
    token = write_credential(data_dir)
    env = os.environ.copy()
    for key in [k for k in env if k.startswith("THE_ONE_") and k != NETNS_SENTINEL]:
        del env[key]
    env["THE_ONE_DATA_DIR"] = str(data_dir)
    env["THE_ONE_DEV_MODE"] = "true"
    # The stub connector type (Library surfaces, M31 F3): this scratch instance only.
    env["THE_ONE_STUB_TEST_ENDPOINT"] = "1"
    env["TZ"] = SERVER_TZ  # pins the server's system zone (tzlocal) for system mode
    env["THE_ONE_OLLAMA_LIBRARY_TEST_JSON"] = json.dumps(OLLAMA_CATALOG)
    logf = open(log, "wb")  # noqa: SIM115 - closed by the caller via proc lifetime
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "the_one.interfaces.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        cwd=cwd,
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=detach,  # --keep-running: survives this script and its tty
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise CaptureError(f"the scratch instance exited early; see {log}")
        try:
            with urllib.request.urlopen(base + "/api/live", timeout=2):  # noqa: S310
                return base, proc, token
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    stop_instance(proc)
    raise CaptureError(f"the scratch instance did not become ready; see {log}")


def stop_instance(proc: subprocess.Popen) -> None:
    """Stop by the recorded PID only."""
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def seed(base: str, token: str, files_root: Path | None = None) -> dict[str, str]:
    ids: dict[str, str] = {}
    for ptype, (name, fields) in PROVIDERS.items():
        row = _api(base, token, "POST", "/api/providers", {"name": name, "type": ptype, **fields})
        ids[ptype] = row["id"]
    name, fields = FLASH_PROVIDER
    ids["flash"] = _api(
        base, token, "POST", "/api/providers", {"name": name, "type": "mock", **fields}
    )["id"]
    _api(
        base,
        token,
        "POST",
        "/api/agents",
        {
            "name": "Capture agent",
            "provider_config_id": ids["mock"],
            "llm_model": "mock-default",
            "system_prompt": "You are a capture-seed agent.",
        },
    )
    seed_tabs_agent(base, token, ids)
    if files_root is not None:
        seed_library(base, token, ids, files_root)
    seed_settings(base, token)
    return ids


TABS_AGENT = "capture-tabs"
CAPTURE_MCP_TOOLS = [
    ("search_docs", "Search the documentation index."),
    ("get_page", "Fetch one page by its path."),
    ("list_spaces", "List the available spaces."),
    ("create_ticket", "Open a ticket in the tracker."),
]


def seed_tabs_agent(base: str, token: str, ids: dict[str, str]) -> None:
    """One agent that exercises every tab of the agent editor (Flight 2 DD10)."""
    ids["agent"] = TABS_AGENT
    ids["kb"] = _api(
        base,
        token,
        "POST",
        "/api/knowledge-bases",
        {"name": "Capture knowledge", "description": "A knowledge base for the capture."},
    )["id"]
    ids["mcpsrc"] = _api(
        base,
        token,
        "POST",
        "/api/mcp-sources",
        {
            "name": "Capture docs server",
            "type": "streamable-http",
            "config": {
                "url": "http://127.0.0.1:9/mcp",
                "_cache": {"tools": [{"name": n, "description": d} for n, d in CAPTURE_MCP_TOOLS]},
            },
            "secrets": {},
        },
    )["id"]
    _api(
        base,
        token,
        "POST",
        "/api/agents",
        {
            "name": TABS_AGENT,
            "description": "An agent that fills every tab, for the UI capture.",
            "provider_config_id": ids["mock"],
            "llm_model": "mock-default",
            "system_prompt": "You answer questions about the capture fixtures, briefly.",
            "kb_ids": [ids["kb"]],
            "mcp_source_ids": [ids["mcpsrc"]],
            # Filesystem is mixed (3 of 9 on), Web is mixed, Execution is all off.
            "enabled_tools": ["read_file", "glob", "list_dir", "fetch_url", "http_request"],
            "disabled_tools": ["delete_file"],
            "tool_overrides": {
                "read_file": {"path_denylist": ["~/.ssh", "~/.aws", "/etc/shadow"]},
            },
        },
    )
    _api(base, token, "POST", f"/api/agents/{TABS_AGENT}/rules", {"text": "Answer in plain words."})
    _api(
        base,
        token,
        "POST",
        f"/api/agents/{TABS_AGENT}/rules",
        {"text": "Never guess a file path.", "enabled": False},
    )
    _api(base, token, "PUT", f"/api/agents/{TABS_AGENT}/notes/settings", {"enabled": True})
    _api(base, token, "POST", f"/api/agents/{TABS_AGENT}/self-configuration")
    return ids


def seed_library(base: str, token: str, ids: dict[str, str], files_root: Path) -> None:
    """A knowledge base with a registered scratch folder (indexed) and a stub connector
    (Flight 3 DD2). ``files_root`` sits beside the scratch data dir, never inside it (a
    folder inside the data dir is refused with 422)."""
    folder = files_root / "library-docs"
    for rel, text in LIBRARY_FILES.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    kbl = _api(
        base,
        token,
        "POST",
        "/api/knowledge-bases",
        {"name": "Capture library", "description": "Four small text files, indexed."},
    )["id"]
    ids["kbl"] = kbl
    _api(
        base,
        token,
        "POST",
        f"/api/knowledge-bases/{kbl}/items",
        {"type": "folder", "path_or_url": str(folder)},
    )
    deadline = time.monotonic() + 90
    status: dict = {}
    while time.monotonic() < deadline:
        status = _api(base, token, "GET", f"/api/knowledge-bases/{kbl}/status")
        if status["items"].get("indexed") == len(LIBRARY_FILES) and status["indexer"] == "idle":
            break
        time.sleep(1)
    else:
        raise CaptureError(f"the capture knowledge base did not finish indexing: {status}")
    ids["conn"] = _api(
        base,
        token,
        "POST",
        "/api/connectors",
        {
            "name": "Capture stub connector",
            "type": "stub",
            "config": {
                "enabled": False,
                "default_agent": "Capture agent",
                "channel_map": {"general": "Capture agent", "support": TABS_AGENT},
            },
            "secrets": {},
        },
    )["id"]


def seed_settings(base: str, token: str) -> None:
    """Operator settings a real install would have (Flight 4 DD2): the time zone in zone
    mode, tools configured and two disabled globally, non-default Knowledge indexing."""
    _put_time_settings(base, token, "zone")
    _api(
        base,
        token,
        "PUT",
        "/api/tools/configs/read_file",
        {
            "enabled": True,
            "config": {
                "path_allowlist": ["~", READ_FILE_ALLOWLIST],
                "read_size_cap_bytes": READ_FILE_SIZE_CAP,
            },
        },
    )
    for name in GLOBALLY_DISABLED_TOOLS:
        _api(base, token, "PUT", f"/api/tools/configs/{name}", {"enabled": False})
    _api(base, token, "PUT", "/api/knowledge-settings", SEED_KNOWLEDGE_SETTINGS)


# ── Capture ──────────────────────────────────────────────────────────────────


def _patch_token_rows(route) -> None:
    resp = route.fetch()
    try:
        data = resp.json()
    except ValueError:
        route.fulfill(response=resp)
        return
    rows = data if isinstance(data, list) else [data]
    for row in rows:
        if isinstance(row, dict) and row.get("type") == "anthropic-plan-token":
            if row.get("token_set_at"):
                row["token_set_at"] = TOKEN_SET_AT
                row["token_expires_around"] = TOKEN_EXPIRES_AROUND
    route.fulfill(response=resp, json=data)


def capture_one(
    browser,
    base: str,
    token: str,
    ids: dict[str, str],
    s: Surface,
    theme: str,
    out: Path,
    width: int = 1280,
):
    viewport = SIZES[width]
    context = browser.new_context(
        viewport=viewport,
        reduced_motion="reduce",
        timezone_id=s.tz,
        locale="en-US",
        color_scheme=theme,
        device_scale_factor=1,
    )
    try:
        context.add_init_script(
            "try { localStorage.setItem('theme-preference', %s); } catch (e) {}" % json.dumps(theme)
        )
        context.add_init_script(DETERMINISM_JS)
        context.route("https://claude.ai/**", lambda r: r.abort())
        # A handoff per context (single-use), through the context's request API.
        r = context.request.post(
            base + "/api/session/handoff", headers={"Authorization": f"Bearer {token}"}
        )
        if not r.ok:
            raise CaptureError(f"{s.name}: handoff mint failed ({r.status})")
        landing = context.request.get(r.json()["url"])
        if not landing.ok:
            raise CaptureError(f"{s.name}: handoff redemption failed ({landing.status})")
        page = context.new_page()
        page.clock.set_fixed_time(FIXED_NOW)
        page.route("**/api/providers", _patch_token_rows)
        page.route("**/api/providers/*", lambda r: _patch_or_continue(r))
        if "ollama" in s.stubs:
            _ollama_stubs(page)
        else:
            page.route(
                "**/api/providers/*/models",
                lambda r: (
                    r.fulfill(json=GENERIC_MODELS) if r.request.method == "GET" else r.continue_()
                ),
            )
        route_hash = s.hash
        for key, value in ids.items():
            route_hash = route_hash.replace("{" + key + "}", value)
        page.goto(base + "/" + route_hash)
        page.locator(s.ready).first.wait_for(state="visible", timeout=20000)
        text = page.locator("body").inner_text()
        if "Unauthorized" in text or '"detail"' in text[:200]:
            raise CaptureError(f"{s.name}: the page is the unauthenticated state")
        if s.prepare:
            s.prepare(Ctx(page, base, ids, theme, token))
        _mask(page)  # every surface: run-to-run values pinned in their own shape
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(500)  # transitions settle; the flash is visible for 5 s
        target = out / f"{s.name}--{theme}--{width}.png"
        if s.shot:
            page.locator(s.shot).first.screenshot(path=str(target), animations="disabled")
        else:
            # The shell scrolls inside panes, so a full-page shot needs a taller viewport:
            # grow it by the largest hidden overflow, then shoot the whole page.
            excess = page.evaluate(
                "() => Math.max(0, ...Array.from(document.querySelectorAll('*')).filter("
                "e => !e.closest('[role=listbox]') && e.scrollHeight > e.clientHeight + 1"
                " && /(auto|scroll)/.test("
                "getComputedStyle(e).overflowY)).map(e => e.scrollHeight - e.clientHeight))"
            )
            if excess:
                page.set_viewport_size(
                    {"width": viewport["width"], "height": viewport["height"] + excess}
                )
                page.wait_for_timeout(300)
            page.screenshot(path=str(target), animations="disabled", full_page=True)
        return target
    finally:
        context.close()
        if s.restore is not None:
            s.restore(base, token, ids)
        if s.name == "flash-after-save":  # undo the rename so the next theme starts clean
            name, fields = FLASH_PROVIDER
            _api(
                base,
                token,
                "PUT",
                f"/api/providers/{ids['flash']}",
                {"name": name, "type": "mock", **fields},
            )


def _patch_or_continue(route) -> None:
    if (
        route.request.method == "GET"
        and route.request.url.rstrip("/").count("/api/providers/") == 1
    ):
        tail = route.request.url.split("/api/providers/", 1)[1]
        if "/" not in tail.split("?")[0]:
            _patch_token_rows(route)
            return
    route.fallback()


# ── CLI ──────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", help="output directory (outside the repo; empty unless --force)")
    p.add_argument("--surfaces", help="comma-separated surface names to capture")
    p.add_argument("--list", action="store_true", help="print the surface table and exit")
    p.add_argument("--keep", action="store_true", help="keep the scratch data tree")
    p.add_argument("--force", action="store_true", help="allow a non-empty --out")
    p.add_argument(
        "--widths",
        default=",".join(str(w) for w in SIZES),
        help="comma-separated viewport widths to capture (default: %(default)s)",
    )
    p.add_argument(
        "--keep-running",
        action="store_true",
        help="start and seed the scratch instance, print its URL/port/data dir/PID, and exit "
        "leaving it running (no --out needed; the HAT reuses the seed)",
    )
    return p.parse_args(argv)


def maybe_reexec_in_netns(argv: list[str]) -> None:
    if os.environ.get("THE_ONE_TEST_NETNS") != "1" or os.environ.get(NETNS_SENTINEL):
        return
    probe = subprocess.run(
        ["unshare", "-rn", "sh", "-c", "ip link set lo up"], capture_output=True, text=True
    )
    if probe.returncode != 0:
        raise CaptureError(
            "THE_ONE_TEST_NETNS=1 but 'unshare -rn' + 'ip link set lo up' is unavailable here "
            "(need util-linux unshare, iproute2 ip, unprivileged user namespaces). "
            "Unset THE_ONE_TEST_NETNS to run without isolation."
        )
    print("ui_capture: re-running in an isolated loopback-only network namespace", file=sys.stderr)
    env = dict(os.environ, **{NETNS_SENTINEL: "1"})
    os.execvpe(
        "unshare",
        ["unshare", "-rn", "sh", "-c", 'ip link set lo up && exec "$@"', "sh", sys.executable]
        + [str(Path(__file__).resolve())]
        + argv,
        env,
    )


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def keep_running(port: int, scratch: Path) -> int:
    """Start and seed the scratch instance, print how to reach it, leave it running.

    The server is detached into its own session so it outlives this script. It is not
    run in a network namespace (a browser outside it could not reach the server), and
    the scratch tree is kept. Stop it by the printed PID only."""
    data_dir = scratch / "data"
    base, proc, token = start_instance(
        port, data_dir, scratch / "cwd", scratch / "serve.log", detach=True
    )
    try:
        seed(base, token, scratch / "home")
    except BaseException:
        stop_instance(proc)
        raise
    print(f"URL:        {base}/")
    print(f"port:       {port}")
    print(f"data dir:   {data_dir}")
    print(f"PID:        {proc.pid}")
    print(f"credential: {data_dir / 'api-credential'}")
    print(f"log:        {scratch / 'serve.log'}")
    print(f"stop with:  kill {proc.pid}")
    return 0


def run(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.list:
        print_table()
        return 0
    if args.keep_running and args.out:
        raise CaptureError("--keep-running takes no --out (it captures nothing)")
    if not args.keep_running and not args.out:
        raise CaptureError("--out DIR is required")
    widths = [int(w) for w in args.widths.split(",") if w.strip()]
    if unknown_w := [w for w in widths if w not in SIZES]:
        raise CaptureError(f"unknown width(s) {unknown_w}; known: {sorted(SIZES)}")
    out = Path(args.out).expanduser().resolve() if args.out else None
    # Refusals that need nothing started come before the namespace re-run.
    port = pick_port()
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    scratch = Path.home() / ".cache" / "the-one-ui-capture" / run_id
    data_dir = scratch / "data"
    check_capture_safety(
        port,
        data_dir,
        out if out is not None else scratch,
        default_data_dir(),
        collect_env_data_dirs(dict(os.environ), REPO_ROOT),
        REPO_ROOT,
    )
    if args.keep_running:
        return keep_running(port, scratch)
    if out.exists() and any(out.iterdir()) and not args.force:
        raise CaptureError(f"--out {out} is not empty; pass --force to write into it")
    maybe_reexec_in_netns(argv)

    wanted = [n.strip() for n in args.surfaces.split(",")] if args.surfaces else None
    known = {s.name for s in SURFACES}
    if wanted and (unknown := [n for n in wanted if n not in known]):
        raise CaptureError(f"unknown surface(s): {', '.join(unknown)} (see --list)")
    todo = [s for s in SURFACES if wanted is None or s.name in wanted]

    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    proc = None
    captured: list[str] = []
    failed: list[dict] = []
    try:
        base, proc, token = start_instance(port, data_dir, scratch / "cwd", scratch / "serve.log")
        ids = seed(base, token, scratch / "home")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=CHROMIUM_DETERMINISM_ARGS)
            try:
                for s in todo:
                    if s.skipped:
                        continue
                    for theme in THEMES:
                        for width in widths:
                            try:
                                path = capture_one(browser, base, token, ids, s, theme, out, width)
                                captured.append(path.name)
                                print(f"captured {path.name}")
                            except Exception as exc:  # keep going; report at the end
                                failed.append(
                                    {
                                        "surface": s.name,
                                        "theme": theme,
                                        "width": width,
                                        "error": str(exc)[:300],
                                    }
                                )
                                print(
                                    f"FAILED {s.name}--{theme}--{width}: {str(exc)[:200]}",
                                    file=sys.stderr,
                                )
            finally:
                browser.close()
    finally:
        if proc is not None:
            stop_instance(proc)
        if not args.keep:
            shutil.rmtree(scratch, ignore_errors=True)
    skipped = [{"surface": s.name, "reason": s.skipped} for s in todo if s.skipped]
    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git("rev-parse", "HEAD"),
        "git_status": _git("status", "--short").splitlines(),
        "viewports": {str(w): SIZES[w] for w in widths},
        "server_time_zone": SERVER_TZ,
        "seed_operator_zone": SEED_ZONE,
        "full_page": True,
        "themes": list(THEMES),
        "browser_time_zone": {x.name: x.tz for x in todo if x.tz != "UTC"} | {"default": "UTC"},
        "locale": "en-US",
        "fixed_clock": FIXED_NOW.isoformat(),
        "captured": captured,
        "failed": failed,
        "skipped": skipped,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for item in skipped:
        print(f"SKIPPED {item['surface']}: {item['reason']}")
    print(f"{len(captured)} PNGs, {len(failed)} failed, {len(skipped)} skipped -> {out}")
    return 1 if failed else 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except CaptureError as exc:
        print(f"ui_capture: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
