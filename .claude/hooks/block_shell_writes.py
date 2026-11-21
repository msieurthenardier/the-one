#!/usr/bin/env python3
"""PreToolUse hook (Bash): refuse shell writes into the source tree (squawk 0292).

Squawk 0286: source, tests, docs, scripts, missions, evals, sorties and squawks (and the
repo-root CLAUDE.md, SECURITY-MODEL.md and README.md, squawk 0385) are changed only with the
Edit/Write tools. A written rule did not hold for autonomous crew, so this hook enforces it.

Contract (Claude Code PreToolUse hooks): the hook JSON arrives on stdin
(``tool_name``, ``tool_input.command``, ``cwd``); exit 2 blocks the call and feeds stderr to the
model; any other exit lets it through. Stdlib only, run with ``python3``.

FAIL OPEN: unparseable stdin, a non-Bash tool, a missing command, or any internal error exits 0.
A guard must never wedge the session; the cost is that an exotic command can slip past.

What it blocks (target path under the_one/ tests/ docs/ scripts/ missions/ evals/ sorties/
squawks/, or exactly CLAUDE.md, SECURITY-MODEL.md or README.md at the repo root, relative to
the command's directory or absolute under the repo root):
  * an output redirect (`>`, `>>`, `>|`, `&>`) whose target is such a path
  * `sed -i` / `--in-place`, `perl -i` (any flag cluster with i), `tee`, `truncate`, `dd of=`
    naming such a path
  * `cp` / `install` / `rsync` whose destination (last operand, or -t DIR) is such a path
  * `mv` with any operand in such a path (moving a source file out edits the tree too)
  * `python -c` / heredoc'd or `-e` inline scripts (python*, perl, ruby, node) that both mention
    such a path and contain a file-write call (open(..., 'w'), write_text, shutil.copy, ...);
    this check reads the raw command text (it is deliberately coarse: any interpreter segment
    plus a path mention plus a write call anywhere in the command)
  * the same rules inside `bash -c "..."`, `eval "..."`, a shell fed a heredoc, `xargs CMD`,
    and `find ... -exec CMD`

Quoting: a small tokenizer (not shlex, which cannot tell a quoted `>` from an operator) honours
single quotes, double quotes, backslashes and `#` comments, so `grep '>' tests/x.py` and
`echo "a > b"` are plain words. Heredoc bodies are skipped for redirect scanning (and scanned as
script text for interpreters and as commands for shells). `$(...)` inside double quotes and
unknown `$VARS` in a path are not expanded; `$HOME`, `~` and `$CLAUDE_PROJECT_DIR` are.

Not covered: a script FILE that writes (`python helper.py`), `git apply` / `patch`, `rm`,
`touch`, and anything built at run time. The test is the verification, not a sandbox.
"""

import json
import os
import posixpath
import re
import sys

PROTECTED = ("the_one", "tests", "docs", "scripts", "missions", "evals", "sorties", "squawks")
# repo-root documents: matched as the exact path relative to the repo root (squawk 0385)
PROTECTED_FILES = ("CLAUDE.md", "SECURITY-MODEL.md", "README.md")
ROOT = os.path.normpath(
    os.environ.get("CLAUDE_PROJECT_DIR")
    or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
ROOTS = {ROOT, os.path.realpath(ROOT)}

OPCHARS = set(";&|<>()")
WRAPPERS = {"sudo", "env", "command", "time", "nohup", "nice", "exec", "builtin", "timeout"}
SHELLS = {"bash", "sh", "zsh", "dash"}
MAX_DEPTH = 4


# --------------------------------------------------------------------------- tokenizer
def tokenize(cmd):
    """Return (tokens, heredoc_bodies). A token is (kind, text); kind in w|redir|in|sep."""
    toks, bodies, pending = [], [], []
    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if c in " \t\r":
            i += 1
        elif c == "\n":
            toks.append(("sep", "\n"))
            i += 1
            for strip, delim in pending:
                lines = []
                while i < n:
                    j = cmd.find("\n", i)
                    j = n if j < 0 else j
                    line = cmd[i:j]
                    i = min(j + 1, n)
                    if (line.lstrip("\t") if strip else line) == delim:
                        break
                    lines.append(line)
                bodies.append("\n".join(lines))
            pending = []
        elif c == "#":
            while i < n and cmd[i] != "\n":
                i += 1
        elif c in OPCHARS:
            j = i
            while j < n and cmd[j] in OPCHARS:
                j += 1
            run = cmd[i:j]
            i = j
            if run.startswith("<<") and not run.startswith("<<<"):
                strip = run.startswith("<<-")
                if i < n and cmd[i] == "-":
                    strip, i = True, i + 1
                while i < n and cmd[i] in " \t":
                    i += 1
                delim, i = read_word(cmd, i)
                pending.append((strip, delim))
            elif ">" in run:
                toks.append(("redir", run))
            elif "<" in run:
                toks.append(("in", run))
            else:
                toks.append(("sep", run))
        else:
            word, i = read_word(cmd, i)
            toks.append(("w", word))
    return toks, bodies


def read_word(cmd, i):
    n, out = len(cmd), []
    while i < n:
        c = cmd[i]
        if c in " \t\r\n" or c in OPCHARS:
            break
        if c == "\\":
            if i + 1 < n and cmd[i + 1] != "\n":
                out.append(cmd[i + 1])
            i += 2
        elif c == "'":
            j = cmd.find("'", i + 1)
            j = n if j < 0 else j
            out.append(cmd[i + 1 : j])
            i = j + 1
        elif c == '"':
            i += 1
            while i < n and cmd[i] != '"':
                if cmd[i] == "\\" and i + 1 < n and cmd[i + 1] in '"\\$`':
                    i += 1
                out.append(cmd[i])
                i += 1
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out), i


def segments(toks):
    """Split on separators; yield (words, redirect_targets) per command segment."""
    words, redirs, k = [], [], 0
    out = []
    while k < len(toks):
        kind, text = toks[k]
        if kind == "sep":
            if words or redirs:
                out.append((words, redirs))
            words, redirs = [], []
        elif kind == "redir":
            if k + 1 < len(toks) and toks[k + 1][0] == "w":
                redirs.append(toks[k + 1][1])
                k += 1
        elif kind == "in":
            if k + 1 < len(toks) and toks[k + 1][0] == "w":
                k += 1
        else:
            words.append(text)
        k += 1
    if words or redirs:
        out.append((words, redirs))
    return out


# --------------------------------------------------------------------------- paths
def is_protected(path, cwd):
    if not path or path == "-":
        return False
    p = os.path.expanduser(path)
    p = p.replace("$CLAUDE_PROJECT_DIR", ROOT).replace("${CLAUDE_PROJECT_DIR}", ROOT)
    p = p.replace("${HOME}", os.path.expanduser("~")).replace("$HOME", os.path.expanduser("~"))
    if "$" in p or "`" in p:
        return False  # unknown variable: cannot resolve, let it through
    if not p.startswith("/"):
        p = posixpath.join(cwd, p)
    p = posixpath.normpath(p)
    for root in ROOTS:
        if p == root or p.startswith(root + "/"):
            rel = p[len(root) :].lstrip("/")
            if rel.split("/")[0] in PROTECTED or rel in PROTECTED_FILES:
                return True
    return False


_dirs = "|".join(PROTECTED)
_files = "|".join(re.escape(f) for f in PROTECTED_FILES)
MENTION = re.compile(
    r"(?<![\w./-])(?:\./)?(?:{d})/|(?:{r})/(?:{d})/"
    r"|(?<![\w./-])(?:\./)?(?:{f})(?![\w.-])|(?:{r})/(?:{f})(?![\w.-])".format(
        d=_dirs, f=_files, r="|".join(re.escape(r) for r in ROOTS)
    )
)
_NEST = r"(?:[^()]|\([^()]*\))*?"
WRITE_CALL = re.compile(
    r"open\s*\(" + _NEST + r",\s*(?:mode\s*=\s*)?['\"][rbt]*[wxa+][rwxabt+]*['\"]"
    r"|\.(?:write_text|write_bytes|unlink|rename|replace)\s*\("
    r"|shutil\.\w+\s*\(|os\.(?:rename|replace|remove|unlink|makedirs)\s*\("
    r"|\.(?:writeFile|writeFileSync|appendFile\w*|rename\w*|unlink\w*|copyFile\w*)\s*\("
    r"|\bFile\.(?:write|rename|delete)\b|\bFile\.open\s*\(" + _NEST + r"['\"][wa]"
    r"|\bopen\s*\(?\s*\w+\s*,\s*['\"]\s*\+?>"
)


# --------------------------------------------------------------------------- analysis
def strip_wrappers(words):
    k = 0
    while k < len(words):
        w = words[k]
        base = posixpath.basename(w)
        if re.match(r"^[A-Za-z_]\w*=", w):
            k += 1
        elif base in WRAPPERS:
            k += 1
            while k < len(words) and (
                words[k].startswith("-") or (base == "timeout" and re.match(r"^\d", words[k]))
            ):
                k += 1
        else:
            break
    return words[k:]


def operands(args):
    return [a for a in args if not a.startswith("-") or a == "-"]


def check_segment(words, redirs, cwd, bodies, depth, raw=""):
    for target in redirs:
        if is_protected(target, cwd):
            return "output redirect into " + target
    words = strip_wrappers(words)
    if not words:
        return None
    cmd, args = posixpath.basename(words[0]), words[1:]
    ops = operands(args)

    if cmd == "sed":
        inplace = any(
            a.startswith("--in-place") or re.match(r"^-[A-Za-z]*i", a)
            for a in args
            if not a.startswith("---")
        )
        if inplace:
            hit = next((a for a in ops if is_protected(a, cwd)), None)
            if hit:
                return "sed -i on " + hit
    elif cmd == "perl":
        if any(re.match(r"^-[A-Za-z]*i", a) for a in args):
            hit = next((a for a in ops if is_protected(a, cwd)), None)
            if hit:
                return "perl -i on " + hit
    elif cmd in ("tee", "truncate"):
        hit = next((a for a in ops if is_protected(a, cwd)), None)
        if hit:
            return cmd + " to " + hit
    elif cmd == "dd":
        hit = next((a[3:] for a in args if a.startswith("of=") and is_protected(a[3:], cwd)), None)
        if hit:
            return "dd of=" + hit
    elif cmd in ("cp", "install", "rsync"):
        dest = None
        for k, a in enumerate(args):
            if a in ("-t", "--target-directory") and k + 1 < len(args):
                dest = args[k + 1]
            elif a.startswith("--target-directory="):
                dest = a.split("=", 1)[1]
        if dest is None and len(ops) >= 2:
            dest = ops[-1]
        if dest and is_protected(dest, cwd):
            return cmd + " into " + dest
    elif cmd == "mv":
        hit = next((a for a in ops if is_protected(a, cwd)), None)
        if hit:
            return "mv involving " + hit
    elif cmd in SHELLS or cmd == "eval":
        if depth < MAX_DEPTH:
            scripts = []
            if cmd == "eval":
                scripts = [" ".join(args)]
            elif "-c" in args and args.index("-c") + 1 < len(args):
                scripts = [args[args.index("-c") + 1]]
            elif not ops:
                scripts = bodies  # shell fed a heredoc
            for s in scripts:
                reason = check_command(s, cwd, depth + 1)
                if reason:
                    return reason
    elif cmd == "xargs" or (cmd == "find" and any(a in ("-exec", "-execdir") for a in args)):
        if cmd == "xargs":
            sub = args[:]
            while sub and sub[0].startswith("-"):
                sub = sub[1:]
        else:
            k = next(k for k, a in enumerate(args) if a in ("-exec", "-execdir"))
            sub = args[k + 1 :]
            scope = [a for a in args[:k] if is_protected(a, cwd)]
            reason = check_segment(sub, [], cwd, bodies, depth)
            if reason is None and scope and sub:
                # `find tests -exec sed -i ... {}`: the find roots are the targets
                probe = sub[:1] + [s for s in sub[1:] if not s.startswith("{")] + scope
                reason = check_segment(probe, [], cwd, bodies, depth)
            return reason
        if sub:
            return check_segment(sub, [], cwd, bodies, depth)
    if re.match(r"^(python[\d.]*|perl|ruby|node|nodejs)$", cmd):
        # raw text, not the tokenized words: the tokenizer drops the quotes the script needs
        text = "\n".join([raw] + bodies)
        if MENTION.search(text) and WRITE_CALL.search(text):
            return "inline " + cmd + " script writing into the tree"
    return None


def check_command(cmd, cwd, depth=0):
    toks, bodies = tokenize(cmd)
    for words, redirs in segments(toks):
        stripped = strip_wrappers(words)
        if stripped and stripped[0] in ("cd", "pushd") and len(stripped) > 1:
            target = os.path.expanduser(stripped[1])
            if "$" not in target:
                cwd = posixpath.normpath(posixpath.join(cwd, target))
            continue
        reason = check_segment(words, redirs, cwd, bodies, depth, cmd)
        if reason:
            return reason
    return None


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name", "Bash") != "Bash":
            return 0
        command = (data.get("tool_input") or {}).get("command")
        if not isinstance(command, str) or not command.strip():
            return 0
        cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else ROOT
        reason = check_command(command, posixpath.normpath(cwd))
    except Exception:  # fail open: never wedge the session
        return 0
    if reason:
        sys.stderr.write(
            "Blocked shell write into the source tree (%s): change files under the_one/, tests/,"
            " docs/, scripts/, missions/, evals/, sorties/ and squawks/ (and the root CLAUDE.md,"
            " SECURITY-MODEL.md and README.md) only with the Edit/Write tools"
            " (squawk 0286, hook squawk 0292).\n" % reason
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
