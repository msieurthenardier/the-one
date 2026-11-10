# ruff: noqa: E501  (the pinned strings are compared verbatim; wrapping them would change the pin)
"""M35 F2 L1 and L3 (DD2, DD6, DD8): the widget frame's document is pinned.

``App.ui.widgetFrame.buildDocument`` is run under node and compared with a literal expected
string: the six fixed parts in order (doctype, charset, policy, viewport, base style, prelude),
then the model's source with exactly one rewrite applied, the link tags (DD6). The prelude is a
reviewed constant, held verbatim in ``tests/fixtures/widgets/pinned-prelude.js``: changing it
fails here, on purpose. Leg 3 filled the ``/* PAUSE-GATE */`` slot and re-pinned it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WIDGET_FRAME_JS = (
    Path(__file__).resolve().parent.parent
    / "the_one"
    / "interfaces"
    / "web"
    / "static"
    / "js"
    / "ui"
    / "widget-frame.js"
)
PINNED_PRELUDE = Path(__file__).resolve().parent / "fixtures" / "widgets" / "pinned-prelude.js"

SCRIPT = """
global.window = global;
global.App = { ui: {} };
const fs = require('fs');
eval(fs.readFileSync(process.argv[1], 'utf8'));
const args = JSON.parse(process.argv[2]);
console.log(JSON.stringify(App.ui.widgetFrame.buildDocument(args.source, args.opts)));
"""

SCRIPT_REGEX = """
global.window = global;
global.App = { ui: {} };
const fs = require('fs');
eval(fs.readFileSync(process.argv[1], 'utf8'));
console.log(JSON.stringify({ source: App.ui.widgetFrame.LINK_RE.source, flags: App.ui.widgetFrame.LINK_RE.flags, prelude: App.ui.widgetFrame.PRELUDE }));
"""

POLICY = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data: blob:; media-src 'none'; font-src 'none'; connect-src 'none'; "
    "frame-src 'none'; child-src 'none'; worker-src 'none'; object-src 'none'; "
    "manifest-src 'none'; form-action 'none'; base-uri 'none'"
)

PRELUDE = PINNED_PRELUDE.read_text().rstrip("\n")

VARS = {
    "--bg": "#101114",
    "--surface": "#17181c",
    "--fg": "#ececf0",
    "--fg-muted": "#8f9199",
    "--border": "#26272c",
    "--accent": "#a78bfa",
    "--danger": "#f87171",
    **{f"--chart-{i}": f"#00000{i}" for i in range(1, 9)},
}

BASE_STYLE = (
    ":root{--bg:#101114;--surface:#17181c;--fg:#ececf0;--fg-muted:#8f9199;--border:#26272c;"
    "--accent:#a78bfa;--danger:#f87171;--chart-1:#000001;--chart-2:#000002;--chart-3:#000003;"
    "--chart-4:#000004;--chart-5:#000005;--chart-6:#000006;--chart-7:#000007;--chart-8:#000008;"
    "--frame-mode:dark;--frame-paused:0;color-scheme:dark}"
    "html,body{margin:0}"
    "html{background:var(--surface);color:var(--fg);font-family:system-ui,-apple-system,sans-serif}"
)

# The one rewrite the page applies to the model's source (DD6); the pin test mirrors it here.
LINK_REWRITE = re.compile(r"<(/?)link(?=[\s/>])", re.IGNORECASE)


def build(source: str, opts: dict) -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    out = subprocess.run(
        [node, "-e", SCRIPT, str(WIDGET_FRAME_JS), json.dumps({"source": source, "opts": opts})],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def expected(source: str, base_style: str = BASE_STYLE) -> str:
    return (
        "<!doctype html>"
        '<meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{POLICY}">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<style>{base_style}</style>"
        f"<script>{PRELUDE}</script>"
        f"{LINK_REWRITE.sub(r'<\1x-link', source)}"
    )


def test_document_is_exactly_the_pinned_text() -> None:
    doc = build("<p>X</p>", {"vars": VARS, "mode": "dark"})
    assert doc == expected("<p>X</p>")


def test_source_is_appended_after_the_prelude_with_only_link_tags_rewritten() -> None:
    """DD6: the body is the source with exactly the link rewrite applied and nothing else changed:
    a hostile policy or base tag, a stray closing script tag, NUL and a lone surrogate all stay."""
    source = (
        '</script><meta http-equiv="Content-Security-Policy" content="default-src *">'
        "<base href=//evil><html><head></head>\x00\ud800 end"
        '<link rel=preconnect href="http://x/"><LINK rel=a></Link><linkx><link/><link\t>'
        "<svg><link></svg> a <li nk> <l ink>"
    )
    doc = build(source, {"vars": VARS, "mode": "dark"})
    body = doc[doc.index("</script>") + len("</script>") :]
    assert body == LINK_REWRITE.sub(r"<\1x-link", source)
    # Only link tags changed: undoing the rewrite gives the source back, byte for byte.
    assert body.replace("<x-link", "<link").replace("</x-link", "</link") == source.replace(
        "<LINK", "<link"
    ).replace("</Link", "</link")
    assert doc == expected(source)
    # A tag that is not a link (a longer name, a split name) is left alone.
    assert "<linkx>" in body and "<li nk>" in body and "<l ink>" in body


def test_prelude_sections_are_in_order() -> None:
    doc = build("X", {"vars": VARS, "mode": "dark"})
    markers = [
        "var ct = W.clearTimeout",  # 1 capture (timers, gesture times)
        "var lastG = -100000;",  # 1 capture: the gesture clock
        'lock(W, "RTCPeerConnection"',  # 2 neuter
        "function okFocus()",  # 2 neuter: the focus gate
        "var LRE = ",  # 2 neuter: the link entry points
        "var paused = false, round = false",  # 3 the pause gate
        "function applyTheme",  # 4 size and theme handlers
    ]
    positions = [doc.index(m) for m in markers]
    assert positions == sorted(positions)
    # The gate slot marker is gone: leg 3 filled it.
    assert "/* PAUSE-GATE */" not in doc
    # The first statement that arms the gate state comes before any handler.
    assert doc.index("var root = D.documentElement;") > doc.index("freeze();")


def test_light_mode_and_missing_vars() -> None:
    doc = build("X", {"vars": {"--bg": "#fff"}, "mode": "light"})
    assert ":root{--bg:#fff;--frame-mode:light;--frame-paused:0;color-scheme:light}" in doc


def test_paused_option_is_written_into_the_base_style() -> None:
    doc = build("X", {"vars": VARS, "mode": "dark", "paused": True})
    assert "--frame-mode:dark;--frame-paused:1;color-scheme:dark}" in doc
    assert doc == expected("X", BASE_STYLE.replace("--frame-paused:0", "--frame-paused:1"))
    # Anything but the boolean true leaves it running.
    assert "--frame-paused:0" in build("X", {"vars": VARS, "mode": "dark", "paused": "yes"})


def test_token_values_cannot_break_out_of_the_style() -> None:
    doc = build("X", {"vars": {"--bg": "red}</style><script>x</script>{"}, "mode": "dark"})
    style = doc[doc.index("<style>") : doc.index("</style>") + 8]
    assert style.count("<") == 2  # only the open and close tag


def test_the_page_and_prelude_link_patterns_are_identical() -> None:
    """The page-side pattern and the prelude's copy must stay the same (DD6): the prelude's source
    line holds exactly the page pattern's source and flags."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    out = subprocess.run(
        [node, "-e", SCRIPT_REGEX, str(WIDGET_FRAME_JS)],
        capture_output=True,
        text=True,
        check=True,
    )
    res = json.loads(out.stdout)
    assert f"var LRE = /{res['source']}/{res['flags']};" in res["prelude"].splitlines()
    # The prefix-aware pattern differs only by the optional namespace prefix group.
    xre = [ln for ln in res["prelude"].splitlines() if ln.startswith("var XRE = ")]
    assert xre == [
        "var XRE = " + "/" + res["source"].replace("link", "((?:[\\w.-]+:)?)link", 1) + "/gi;"
    ]


def test_prelude_text_is_es5_and_script_safe() -> None:
    """The text lives inside a script element and the library source rules scan its lines."""
    assert "</script" not in PRELUDE.lower() and "<!--" not in PRELUDE
    for token in ("=>", "`", "const ", "let ", "App.", "//"):
        assert token not in PRELUDE, token
