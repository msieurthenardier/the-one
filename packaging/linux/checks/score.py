"""Score one gate-runner evidence directory (packaging checks). Stdlib only.

usage: score.py EVDIR --format F --distro D --image I --n VN [--n1 VN1]

Reads the files gates-inner.sh wrote, writes EVDIR/score.json and prints one summary line.
Nothing here knows which tool built the package.
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

GATE_RE = re.compile(r"^ {2}(?P<name>\S[^:]*): (?P<state>OK|FAIL) — (?P<detail>.*)$")
ALLOWED_SKIP = "window chrome"
# gate-3 library families: (label, path regex matched against the mapped file's path)
LIBS = [
    ("libglib-2.0", r"/libglib-2\.0\.so"),
    ("libgobject-2.0", r"/libgobject-2\.0\.so"),
    ("libgtk-3", r"/libgtk-3\.so"),
    ("libgirepository-2.0", r"/libgirepository-2\.0\.so"),
    ("libwebkit2gtk-4.1", r"/libwebkit2gtk-4\.1\.so"),
    ("libstdc++", r"/libstdc\+\+\.so"),
    ("libgcc_s", r"/libgcc_s\.so"),
    # the AppImage's fallback set (flight 2 DD1): from /usr/lib when the host resolves the
    # soname, from the AppImage only when it does not
    ("libdbusmenu-glib", r"/libdbusmenu-glib\.so"),
    ("libdbusmenu-gtk3", r"/libdbusmenu-gtk3\.so"),
    ("libayatana-ido3", r"/libayatana-ido3-0\.4\.so"),
    ("libayatana-indicator3", r"/libayatana-indicator3\.so"),
    ("libayatana-appindicator3", r"/libayatana-appindicator3\.so"),
]
FALLBACK_SONAME = {
    "libgirepository-2.0": "libgirepository-2.0.so.0",
    "libdbusmenu-glib": "libdbusmenu-glib.so.4",
    "libdbusmenu-gtk3": "libdbusmenu-gtk3.so.4",
    "libayatana-ido3": "libayatana-ido3-0.4.so.0",
    "libayatana-indicator3": "libayatana-indicator3.so.7",
    "libayatana-appindicator3": "libayatana-appindicator3.so.1",
}
# where the AppImage runtime puts the payload: a FUSE mount, or the extract-and-run directory
MOUNT_RE = re.compile(r"^/tmp/(\.mount_[^/]+|appimage_extracted_[^/]+)/")
FALLBACK_RE = re.compile(
    r"^/tmp/(\.mount_[^/]+|appimage_extracted_[^/]+)/usr/lib/gleepglorp-ai-fallback/lib/"
)
# a path value that points into the package: the AppImage payload or the PyInstaller bundle
BUNDLE_RE = re.compile(
    r"/tmp/\.mount_|/tmp/appimage_extracted_|/gleepglorp-ai(-fallback)?(/|$)|/_internal|/opt/m32"
)
LOADER_VARS = (
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "GI_TYPELIB_PATH",
    "GIO_MODULE_DIR",
    "GTK_PATH",
    "XDG_DATA_DIRS",
)
# WebKitWebProcess does not map libgirepository (a C binary)
WEB_IGNORE_MISSING = {"libgirepository-2.0"}


def read(p: Path) -> str:
    try:
        return p.read_text(errors="replace")
    except OSError:
        return ""


def score_doctor(text: str) -> dict:
    """AC1: PASS only if exit 0 and no gate detail says 'skipped' (window chrome excepted)."""
    rc_m = re.findall(r"^rc=(\d+)$", text, re.M)
    rc = int(rc_m[-1]) if rc_m else None
    gates, bad = [], []
    in_runtimes = False
    for line in text.splitlines():
        if line.strip().startswith("runtimes:"):
            in_runtimes = True
            continue
        if in_runtimes:
            continue
        m = GATE_RE.match(line)
        if not m:
            continue
        gates.append((m["name"], m["state"], m["detail"]))
        if m["state"] == "FAIL":
            bad.append(f"{m['name']} FAIL")
        elif "skipped" in m["detail"] and not (
            m["name"] == ALLOWED_SKIP and m["detail"].startswith("skipped (not Windows)")
        ):
            bad.append(f"{m['name']} skipped")
    ok = rc == 0 and not bad and bool(gates)
    return {"pass": ok, "rc": rc, "gates": len(gates), "bad": bad}


def norm(path: str) -> str:
    path = re.sub(r"\s+\(deleted\)$", "", path)
    return "/usr" + path if path.startswith("/lib/") else path


def mapped_files(maps: str) -> set:
    out = set()
    for line in maps.splitlines():
        parts = line.split(None, 5)
        if len(parts) == 6 and parts[5].startswith("/"):
            out.add(norm(parts[5].strip()))
    return out


def host_libs(text: str) -> dict:
    """host-libs.txt from gates-inner.sh: `<soname> yes|no <path>` per fallback soname."""
    out = {}
    for ln in text.splitlines():
        p = ln.split()
        if len(p) >= 2:
            out[p[0]] = p[1] == "yes"
    return out


def score_maps(maps: str, web: bool, appimage: bool = False, host: dict | None = None) -> dict:
    files = mapped_files(maps)
    host = host or {}
    res, ok, why = {}, True, []
    for label, rx in LIBS:
        hits = sorted(f for f in files if re.search(rx, f))
        res[label] = hits
        from_usr = [h for h in hits if h.startswith("/usr/lib/")]
        so = FALLBACK_SONAME.get(label)
        if web:
            good = len(hits) <= 1 and len(from_usr) == len(hits)
        elif appimage and so and host.get(so) is False:
            # the host lacks it: exactly one copy, from the AppImage's fallback directory
            good = len(hits) == 1 and bool(FALLBACK_RE.match(hits[0]))
        elif so and not appimage:
            # the .deb has no preload, so the tray libraries are mapped only if pystray used them
            good = len(hits) <= 1 and len(from_usr) == len(hits)
        else:
            # the host has it (or it is not a fallback library): exactly one copy, from /usr/lib
            good = len(hits) == 1 and len(from_usr) == 1
        if not good:
            why.append(label)
        ok = ok and good
    mounted = sorted(f for f in files if MOUNT_RE.match(f))
    if web and mounted:
        ok = False
        why.append(f"web process maps {len(mounted)} files from the AppImage mount")
    return {"ok": ok, "libs": res, "bad": why}


def score_environ(text: str) -> dict:
    """AC3: none of the loader-affecting variables holds a path into the package."""
    bad = {}
    for ln in text.splitlines():
        k, _, v = ln.partition("=")
        if k in LOADER_VARS and any(BUNDLE_RE.search(part) for part in v.split(":")):
            bad[k] = v
    return {"ok": bool(text) and not bad, "bad": bad}


def hook_report(applog: str) -> dict | None:
    """The rthook's THE_ONE_PKG_DEBUG lines in the app log, or None when it was not enabled."""
    m = re.search(r"fallback sources: (\{.*\})", applog)
    if not m:
        return None
    env = re.search(r"GI_TYPELIB_PATH='([^']*)' LD_LIBRARY_PATH=(\S+)", applog)
    return {
        "sources": ast.literal_eval(m.group(1)),
        "gi_typelib_path": env.group(1) if env else None,
        "ld_library_path": env.group(2) if env else None,
    }


def cross_check(rep: dict, ui_files: set, host: dict, typelib_host: bool) -> list:
    """Compare the hook's own account with the maps and with ldconfig; returns problems."""
    bad = []
    for so, src in rep["sources"].items():
        label = next((k for k, v in FALLBACK_SONAME.items() if v == so), None)
        rx = dict(LIBS).get(label)
        hits = [f for f in ui_files if rx and re.search(rx, f)]
        if src == "host" and (not hits or not hits[0].startswith("/usr/lib/")):
            bad.append(f"{so}: hook says host, maps say {hits}")
        if src == "fallback" and (not hits or not FALLBACK_RE.match(hits[0])):
            bad.append(f"{so}: hook says fallback, maps say {hits}")
        if src == "host" and host.get(so) is False:
            bad.append(f"{so}: hook says host, ldconfig says the host lacks it")
        if src == "fallback" and host.get(so) is True:
            bad.append(f"{so}: hook used the fallback although ldconfig sees the host copy")
    ld = rep["ld_library_path"] or ""
    if BUNDLE_RE.search(ld):
        bad.append(f"LD_LIBRARY_PATH holds a package path: {ld}")
    parts = (rep["gi_typelib_path"] or "").split(":")
    fb = [i for i, p in enumerate(parts) if "gleepglorp-ai-fallback" in p]
    if fb and (typelib_host or fb != [len(parts) - 1]):
        bad.append(f"fallback typelib dir misplaced or not needed: {parts}")
    if not fb and not typelib_host:
        bad.append("host lacks the Ayatana typelib but the fallback typelib dir is not listed")
    return bad


PROBE_FAIL_RE = re.compile(
    r"GLib-CRITICAL|GLib-GObject-(CRITICAL|WARNING)|GLib-GIO-(CRITICAL|WARNING)"
    r"|symbol lookup error|undefined symbol"
)


def score_probe(ev: Path, control: Path | None, expect_fallback: bool) -> dict:
    """AC4: the ABI probe ran clean; lines also seen in the control run are excluded."""
    out, err = read(ev / "probe.stdout"), read(ev / "probe.stderr")
    rc = read(ev / "probe.rc").strip()
    skip = set()
    if control:
        skip = set(read(control / "probe.stderr").splitlines())
    hits = [ln for ln in err.splitlines() if PROBE_FAIL_RE.search(ln) and ln not in skip]
    excluded = [ln for ln in err.splitlines() if PROBE_FAIL_RE.search(ln) and ln in skip]
    maps = [ln[len("PROBE_MAP ") :] for ln in out.splitlines() if ln.startswith("PROBE_MAP ")]
    mapped = {}
    for path in maps:
        mapped.setdefault(norm(path.split()[0]), 0)
    fb_all = bool(maps) and all(FALLBACK_RE.match(p) for p in mapped)
    ok = "PROBE_OK" in out and rc == "rc=0" and not hits
    if expect_fallback:
        ok = ok and fb_all and len(mapped) >= 6
    return {
        "ok": ok,
        "rc": rc,
        "probe_ok": "PROBE_OK" in out,
        "bad_stderr_lines": hits,
        "excluded_as_in_control": excluded,
        "mapped": sorted(mapped),
        "all_from_fallback": fb_all,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ev")
    ap.add_argument("--format", required=True)
    ap.add_argument("--distro", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--n")
    ap.add_argument("--n1")
    ap.add_argument(
        "--window", action="store_true", help="the run had a window phase (implied by baseline)"
    )
    ap.add_argument("--probe", action="store_true", help="score an ABI-probe run instead")
    ap.add_argument("--control", help="probe: a control run whose stderr lines are excluded")
    ap.add_argument(
        "--expect-fallback", action="store_true", help="probe: all six from the AppImage"
    )
    a = ap.parse_args()
    ev = Path(a.ev)
    if a.probe:
        pr = score_probe(ev, Path(a.control) if a.control else None, a.expect_fallback)
        (ev / "probe-score.json").write_text(json.dumps(pr, indent=1))
        print(
            f"probe {a.format}/{a.distro}-{a.image}: {'PASS' if pr['ok'] else 'FAIL'} "
            f"rc={pr['rc']} bad_stderr={len(pr['bad_stderr_lines'])} "
            f"excluded={len(pr['excluded_as_in_control'])} mapped={len(pr['mapped'])} "
            f"all_from_fallback={pr['all_from_fallback']}"
        )
        return 0 if pr["ok"] else 1
    if not a.n:
        ap.error("--n is required")
    r: dict = {"format": a.format, "distro": a.distro, "image": a.image}

    r["g1_pinned"] = score_doctor(read(ev / "doctor-pinned.txt"))
    r["g1_unpinned"] = score_doctor(read(ev / "doctor-unpinned.txt"))

    # gate 2: the resolved interpreter, run independently
    g2 = read(ev / "gate2.txt").splitlines()
    exe_line = next((ln for ln in g2[1:] if " " in ln and ln.startswith("/")), "")
    exe, _, prefix = exe_line.partition(" ")
    ver = next((ln for ln in g2 if ln.startswith("Python ")), "")
    bundle = ("/opt/gleepglorp-ai", "/opt/m32", "/tmp/appimage", "/tmp/.mount", "/_internal")
    r["g2"] = {
        "pass": bool(exe)
        and exe.startswith("/usr/")
        and not any(b in exe + prefix for b in bundle),
        "exe": exe,
        "prefix": prefix.strip(),
        "version": ver.strip(),
    }

    # gate 3 (window runs only: baseline images, and the .deb on a bare image under xvfb)
    windowed = a.image == "baseline" or a.window
    if windowed:
        ui = read(ev / "ui.maps")
        webs = sorted(ev.glob("web-*.maps"))
        appimage = a.format == "appimage"
        host = host_libs(read(ev / "host-libs.txt"))
        if not ui:
            r["g3"] = {
                "pass": False,
                "note": "no UI process with libgtk-3 mapped (window did not open)",
            }
        else:
            uis = score_maps(ui, web=False, appimage=appimage, host=host)
            wsc = [score_maps(w.read_text(errors="replace"), True, appimage, host) for w in webs]
            # AC3 reads the WebKitWebProcess environments only: the UI process's own
            # /proc/<pid>/environ is the initial block the PyInstaller bootloader built (it
            # still names the bundle), which the hook edits in memory; children inherit the edit.
            envs = [score_environ(read(p)) for p in sorted(ev.glob("web-*.environ"))]
            rep = hook_report(read(ev / "app.log"))
            xc = None
            if rep:
                typelib_host = any(host.get(t) for t in host if t.endswith(".typelib"))
                xc = cross_check(rep, mapped_files(ui), host, typelib_host)
            r["g3"] = {
                "pass": uis["ok"]
                and bool(wsc)
                and all(w["ok"] for w in wsc)
                and bool(envs)
                and all(e["ok"] for e in envs)
                and not xc,
                "ui": uis,
                "web_processes": len(wsc),
                "web_ok": [w["ok"] for w in wsc],
                "environ_ok": [e["ok"] for e in envs],
                "environ_bad": [e["bad"] for e in envs if e["bad"]],
                "hook_report": rep,
                "hook_cross_check": xc,
                "note": "" if wsc else "no WebKitWebProcess found - web half not measured",
            }
        shot = ev / "window.png"
        r["screenshot"] = str(shot) if shot.exists() else None
    else:
        r["g3"] = {"pass": None, "note": "N/A (bare image: no window)"}

    # gate 4
    rot = read(ev / "gate4-rotate.txt")
    ls = read(ev / "gate4-ls.txt")
    m = re.search(r"Local API credential created at (\S+)", rot)
    port_ok = read(ev / "serve-N.state").startswith("live")
    r["g4"] = {
        "pass": bool(
            m
            and "/.local/share/the-one/" in m.group(1)
            and port_ok
            and "api-credential" in ls
            and re.search(r"\.db\b", ls)
        ),
        "credential_path": m.group(1) if m else None,
        "serve_live": port_ok,
        "ls": [ln.split()[-1] for ln in ls.splitlines()[3:] if ln.strip()],
    }

    # upgrade
    v_n, v_n1 = read(ev / "version-N.txt"), read(ev / "version-N1.txt")
    p_n, p_n1 = read(ev / "cred-prefix-N.txt").strip(), read(ev / "cred-prefix-N1.txt").strip()
    ag = read(ev / "agents-N1.json")
    r["upgrade"] = (
        {"pass": None, "note": "N/A (single version)"}
        if not a.n1
        else {
            "pass": f"v{a.n}" in v_n
            and f"v{a.n1}" in v_n1
            and "m32-upgrade-agent" in ag
            and bool(p_n)
            and p_n == p_n1,
            "version_N": f"v{a.n}" in v_n,
            "version_N1": f"v{a.n1}" in v_n1,
            "agent_readback": "m32-upgrade-agent" in ag,
            "cred_prefix": p_n,
            "cred_prefix_same": p_n == p_n1,
        }
    )

    # single instance
    si = read(ev / "single-instance.txt")
    if not windowed or not si:
        r["single"] = {
            "pass": None,
            "note": "N/A (no window)" if not windowed else "not run",
        }
    else:
        el = re.search(r"elapsed=([\d.]+)", si)
        socks = re.search(r"sockets on 8490/8491: (\d+)", si)
        focus = read(ev / "focus.txt")
        r["single"] = {
            "pass": "second_state=exited" in si
            and bool(el)
            and float(el.group(1)) <= 10
            and bool(socks)
            and int(socks.group(1)) == 1
            and '"focused":true' in focus.replace(" ", ""),
            "elapsed": el.group(1) if el else None,
            "listeners": socks.group(1) if socks else None,
            "focus": focus.strip()[:120],
        }

    # tray: typelib on host + the desktop-shell gate under each run
    tray = read(ev / "tray.txt")
    r["tray"] = {
        "ayatana_typelib": "AyatanaAppIndicator3-0.1.typelib" in tray
        and "No such file" not in tray.split("\n")[0],
        "shell_pinned": next(
            (
                ln.strip()
                for ln in read(ev / "doctor-pinned.txt").splitlines()
                if "desktop shell" in ln
            ),
            "",
        ),
        "shell_unpinned": next(
            (
                ln.strip()
                for ln in read(ev / "doctor-unpinned.txt").splitlines()
                if "desktop shell" in ln
            ),
            "",
        ),
    }
    (ev / "score.json").write_text(json.dumps(r, indent=1))

    def c(v):
        return {True: "PASS", False: "FAIL", None: "N/A"}[v]

    print(
        f"{a.format}/{a.distro}-{a.image}: G1p={c(r['g1_pinned']['pass'])} "
        f"G1u={c(r['g1_unpinned']['pass'])} "
        f"G2={c(r['g2']['pass'])} G3={c(r['g3']['pass'])} G4={c(r['g4']['pass'])} "
        f"upgrade={c(r['upgrade']['pass'])} single={c(r['single']['pass'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
