"""Score one gate-runner evidence directory (Mission 32 Flight 1 spike). Stdlib only.

usage: score.py EVDIR --format F --distro D --image I --n VN --n1 VN1

Reads the files inner.sh wrote, writes EVDIR/score.json and prints one summary line.
Candidate-neutral: nothing here knows which tool built the package.
"""

import argparse
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
]
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


def score_maps(maps: str, web: bool) -> dict:
    files = mapped_files(maps)
    res, ok = {}, True
    for label, rx in LIBS:
        hits = sorted(f for f in files if re.search(rx, f))
        # normalise versioned names of the same library to one "copy" per directory+family
        host = [h for h in hits if h.startswith("/usr/lib/")]
        res[label] = hits
        if web and label in WEB_IGNORE_MISSING:
            good = len(hits) <= 1 and len(host) == len(hits)
        elif web:
            good = len(hits) <= 1 and len(host) == len(hits)
        else:
            good = len(hits) == 1 and len(host) == 1
        ok = ok and good
    return {"ok": ok, "libs": res}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ev")
    ap.add_argument("--format", required=True)
    ap.add_argument("--distro", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--n", required=True)
    ap.add_argument("--n1", required=True)
    a = ap.parse_args()
    ev = Path(a.ev)
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

    # gate 3 (window images only)
    if a.image == "baseline":
        ui = read(ev / "ui.maps")
        webs = sorted(ev.glob("web-*.maps"))
        if not ui:
            r["g3"] = {
                "pass": False,
                "note": "no UI process with libgtk-3 mapped (window did not open)",
            }
        else:
            uis = score_maps(ui, web=False)
            wsc = [score_maps(w.read_text(errors="replace"), web=True) for w in webs]
            r["g3"] = {
                "pass": uis["ok"] and bool(wsc) and all(w["ok"] for w in wsc),
                "ui": uis,
                "web_processes": len(wsc),
                "web_ok": [w["ok"] for w in wsc],
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
    r["upgrade"] = {
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

    # single instance
    si = read(ev / "single-instance.txt")
    if a.image != "baseline" or not si:
        r["single"] = {
            "pass": None,
            "note": "N/A (no window)" if a.image != "baseline" else "not run",
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
