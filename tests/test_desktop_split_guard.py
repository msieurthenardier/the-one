"""Guard for the desktop shell split (Mission 32, Flight 3, leg 1, DD1).

``shell.py`` shed its takeover, window-control and lifecycle-state code to
``takeover.py``, ``window_control.py`` and ``session_state.py``. A test that still
patches a moved name *through ``shell``* would not fail with
``monkeypatch.setattr(..., raising=False)``; it would just stop patching anything.
This guard parses every ``tests/**/*.py`` and fails, naming file and line, when a
test patches or assigns through the ``shell`` module a name that ``shell.py`` does
not itself define at its top level (``def``, ``class`` or an assignment target).
A name ``shell.py`` merely imports (``__version__``, ``desktop_host``, ``httpx``)
is not allowed either: patch it in the module that uses it.

Detection is by module binding, never by a variable's name, so files where
``shell`` is a tool or an unrelated fixture value are not flagged.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SHELL_MODULE = "the_one.interfaces.desktop.shell"
SHELL_PACKAGE = "the_one.interfaces.desktop"
REPO = Path(__file__).resolve().parent.parent
SHELL_PATH = REPO / "the_one" / "interfaces" / "desktop" / "shell.py"
TESTS = REPO / "tests"


# -- what shell.py defines ---------------------------------------------------


def defined_names(source: str) -> set[str]:
    """Names bound at the top level of ``source`` by def, class or assignment
    (imports are deliberately excluded)."""
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name):
                        names.add(sub.id)
    return names


# -- alias resolution --------------------------------------------------------


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _is_str(node: ast.AST, value: str | None = None) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and (value is None or node.value == value)
    )


def _is_shell_expr(node: ast.AST, aliases: set[str]) -> bool:
    """True when ``node`` evaluates to the shell module."""
    if isinstance(node, ast.Name):
        return node.id in aliases
    if isinstance(node, ast.Attribute):
        return _dotted(node) == SHELL_MODULE
    if isinstance(node, ast.Subscript):  # sys.modules["…shell"]
        return _dotted(node.value) == "sys.modules" and _is_str(node.slice, SHELL_MODULE)
    if isinstance(node, ast.Call):
        dotted = _dotted(node.func)
        if dotted in ("importlib.import_module", "import_module"):
            return bool(node.args) and _is_str(node.args[0], SHELL_MODULE)
        if dotted in ("importlib.reload", "reload"):
            return bool(node.args) and _is_shell_expr(node.args[0], aliases)
    return False


def _own_nodes(scope: ast.AST):
    """Walk ``scope`` without descending into nested function or class bodies."""
    todo = list(ast.iter_child_nodes(scope))
    while todo:
        node = todo.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        todo.extend(ast.iter_child_nodes(node))


def _bound_aliases(scope: ast.AST, inherited: set[str], fixtures: set[str]) -> set[str]:
    """Aliases of the shell module visible inside ``scope`` (to a fixed point)."""
    aliases = set(inherited)
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = scope.args
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            if arg.arg in fixtures:
                aliases.add(arg.arg)
            else:
                aliases.discard(arg.arg)  # a parameter shadows an outer alias
    nodes = list(_own_nodes(scope))
    changed = True
    while changed:
        changed = False
        for node in nodes:
            new: set[str] = set()
            if isinstance(node, ast.Import):
                for item in node.names:
                    if item.name == SHELL_MODULE and item.asname:
                        new.add(item.asname)
            elif isinstance(node, ast.ImportFrom):
                if node.module == SHELL_PACKAGE and node.level == 0:
                    for item in node.names:
                        if item.name == "shell":
                            new.add(item.asname or "shell")
            elif isinstance(node, ast.Assign):
                if _is_shell_expr(node.value, aliases):
                    new.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign):
                if (
                    node.value is not None
                    and isinstance(node.target, ast.Name)
                    and _is_shell_expr(node.value, aliases)
                ):
                    new.add(node.target.id)
            if not new <= aliases:
                aliases |= new
                changed = True
    return aliases


def _is_fixture(func: ast.AST) -> bool:
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for deco in func.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        if (_dotted(target) or "").split(".")[-1] == "fixture":
            return True
    return False


def shell_fixtures(source: str) -> set[str]:
    """Names of fixtures in ``source`` that return (or yield) the shell module."""
    tree = ast.parse(source)
    module_aliases = _bound_aliases(tree, set(), set())
    found: set[str] = set()
    for node in ast.walk(tree):
        if not _is_fixture(node):
            continue
        local = _bound_aliases(node, module_aliases, set())
        for sub in _own_nodes(node):
            if isinstance(sub, (ast.Return, ast.Yield)) and sub.value is not None:
                if _is_shell_expr(sub.value, local):
                    found.add(node.name)
            elif isinstance(sub, ast.Expr) and isinstance(sub.value, ast.Yield):
                if sub.value.value is not None and _is_shell_expr(sub.value.value, local):
                    found.add(node.name)
    return found


# -- the patch and assignment forms ------------------------------------------


def _shell_target_name(arg: ast.AST, name_arg: ast.AST | None, aliases: set[str]) -> str | None:
    """The shell attribute a patch call names, from a dotted string or (module, "name")."""
    if _is_str(arg):
        text = arg.value  # type: ignore[attr-defined]
        if text.startswith(SHELL_MODULE + "."):
            return text[len(SHELL_MODULE) + 1 :].split(".")[0]
        return None
    if name_arg is not None and _is_shell_expr(arg, aliases) and _is_str(name_arg):
        return name_arg.value  # type: ignore[attr-defined]
    return None


def _patched_names(node: ast.AST, aliases: set[str]) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and _is_shell_expr(target.value, aliases):
                hits.append((node.lineno, target.attr))
    elif isinstance(node, ast.Call) and node.args:
        dotted = _dotted(node.func) or ""
        last = dotted.split(".")[-1]
        second = node.args[1] if len(node.args) > 1 else None
        name = None
        if last in ("setattr", "delattr") and dotted != "":
            # monkeypatch.setattr(target, name, value) | monkeypatch.setattr("a.b.c", value)
            # (also the builtin setattr(module, "name", value))
            name = _shell_target_name(node.args[0], second, aliases)
        elif dotted == "patch" or dotted.endswith(".patch"):
            name = _shell_target_name(node.args[0], None, aliases)
        elif dotted.endswith("patch.object"):
            name = _shell_target_name(node.args[0], second, aliases)
        if name is not None:
            hits.append((node.lineno, name))
    return hits


def find_violations(
    source: str, allowed: set[str], conftest_fixtures: set[str] | None = None
) -> list[tuple[int, str]]:
    """``(line, name)`` for each patch or assignment through ``shell`` of a name
    that ``allowed`` (shell.py's own top-level definitions) does not contain."""
    tree = ast.parse(source)
    fixtures = set(conftest_fixtures or ()) | shell_fixtures(source)
    out: list[tuple[int, str]] = []

    def visit(scope: ast.AST, inherited: set[str]) -> None:
        aliases = _bound_aliases(scope, inherited, fixtures)
        for node in _own_nodes(scope):
            for line, name in _patched_names(node, aliases):
                if name not in allowed:
                    out.append((line, name))
        for node in _own_nodes(scope):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(node, aliases)

    visit(tree, set())
    return sorted(set(out))


# -- the guard over the real tree --------------------------------------------


def _conftest_fixtures() -> set[str]:
    return shell_fixtures((TESTS / "conftest.py").read_text(encoding="utf-8"))


def test_no_test_patches_a_name_shell_does_not_define():
    allowed = defined_names(SHELL_PATH.read_text(encoding="utf-8"))
    fixtures = _conftest_fixtures()
    problems = []
    for path in sorted(TESTS.rglob("*.py")):
        if path == Path(__file__).resolve():
            continue
        for line, name in find_violations(path.read_text(encoding="utf-8"), allowed, fixtures):
            problems.append(f"{path.relative_to(REPO)}:{line}: shell.{name}")
    assert not problems, (
        "These tests patch or assign a name through the desktop shell module that shell.py "
        "does not define (it moved to takeover.py, window_control.py or session_state.py, "
        "or it is only imported by shell.py). Patch it in the module that defines or uses "
        "it:\n  " + "\n  ".join(problems)
    )


def test_shell_defines_none_of_the_moved_names():
    defined = defined_names(SHELL_PATH.read_text(encoding="utf-8"))
    moved = {
        "_now", "_sleep", "_parse_version", "_is_older", "_auth_headers", "_running_version",
        "_request_quit", "_pid_alive", "_wait_for_exit", "_activation_token", "_post_focus",
        "_takeover", "_select_port", "_TAKEOVER_WAIT_BOUND", "_TAKEOVER_POLL",
        "_TAKEOVER_NOTICE_AFTER", "_is_gtk_backend", "_on_wayland", "_mark_visible",
        "_show_window", "_gtk_read", "window_visible", "_window_mapped", "_mode",
        "window_state", "quit_desktop", "_gtk_activate", "focus_window", "set_window_theme",
        "_no_tray_hide", "_NO_TRAY_NOTICE_SUMMARY", "_NO_TRAY_NOTICE_BODY", "_clear_booting",
        "_really_quit", "_desktop_window", "_tray_mode", "_session", "_tracked_visible",
        "_booting", "_quit_requested", "_browser_server", "_window_lock",
    }  # fmt: skip
    assert not (defined & moved), sorted(defined & moved)


# -- the guard's own tests, on synthetic sources -----------------------------

ALLOWED = {"DesktopSession", "run_desktop", "_webview_available", "_TRAY_NOTICE_BODY"}
SHELL_DOTTED = SHELL_MODULE
ALIAS_FORMS = {
    "import-as": f"import {SHELL_DOTTED} as A\n",
    "from-import": f"from {SHELL_PACKAGE} import shell as A\n",
    "from-import-plain": f"from {SHELL_PACKAGE} import shell\nA = shell\n",
    "from-import-multi": f"from {SHELL_PACKAGE} import host, shell as A\n",
    "sys-modules": f'import sys\nA = sys.modules["{SHELL_DOTTED}"]\n',
    "import-module": f'import importlib\nA = importlib.import_module("{SHELL_DOTTED}")\n',
    "alias-of-alias": f"from {SHELL_PACKAGE} import shell as B\nA = B\n",
    "reload": (
        f"import importlib\nfrom {SHELL_PACKAGE} import shell as B\nA = importlib.reload(B)\n"
    ),
}
PATCH_FORMS = {
    "setattr-string": 'monkeypatch.setattr("%s.X", 1)' % SHELL_DOTTED,
    "setattr-alias": 'monkeypatch.setattr(A, "X", 1)',
    "setattr-raising-false": 'monkeypatch.setattr(A, "X", 1, raising=False)',
    "mock-patch-string": 'patch("%s.X")' % SHELL_DOTTED,
    "mock-patch-qualified": 'mock.patch("%s.X")' % SHELL_DOTTED,
    "patch-object": 'patch.object(A, "X")',
    "assignment": "A.X = 1",
}


@pytest.mark.parametrize("form", sorted(ALIAS_FORMS))
@pytest.mark.parametrize("scope", ["module", "function"])
def test_each_alias_form_is_caught(form, scope):
    patch = 'monkeypatch.setattr(A, "X", 1)'
    if scope == "module":
        src = ALIAS_FORMS[form] + f"\ndef test_x(monkeypatch):\n    {patch}\n"
    else:
        body = "".join("    " + ln + "\n" for ln in ALIAS_FORMS[form].splitlines())
        src = f"def test_x(monkeypatch):\n{body}    {patch}\n"
    assert [name for _, name in find_violations(src, ALLOWED)] == ["X"]


@pytest.mark.parametrize("form", sorted(PATCH_FORMS))
def test_each_patch_form_is_caught(form):
    src = ALIAS_FORMS["import-as"] + f"\ndef test_x(monkeypatch):\n    {PATCH_FORMS[form]}\n"
    assert [name for _, name in find_violations(src, ALLOWED)] == ["X"]


def test_a_violation_names_its_line():
    src = (
        ALIAS_FORMS["import-as"]
        + '\n\ndef test_x(monkeypatch):\n    monkeypatch.setattr(A, "X", 1)\n'
    )
    assert find_violations(src, ALLOWED) == [(5, "X")]


def test_an_imported_but_not_defined_name_is_caught():
    # shell.py imports __version__ and desktop_host; it does not define them.
    allowed = defined_names("from the_one import __version__\nimport httpx\ndef f():\n    pass\n")
    assert allowed == {"f"}
    src = ALIAS_FORMS["import-as"] + (
        '\ndef test_x(monkeypatch):\n    monkeypatch.setattr(A, "__version__", "1")\n'
        '    monkeypatch.setattr(A, "httpx", None, raising=False)\n'
    )
    assert [n for _, n in find_violations(src, allowed)] == ["__version__", "httpx"]


def test_an_allowed_name_passes():
    src = ALIAS_FORMS["import-as"] + (
        '\ndef test_x(monkeypatch):\n    monkeypatch.setattr(A, "run_desktop", 1)\n'
        '    patch.object(A, "_webview_available")\n    A._TRAY_NOTICE_BODY = "x"\n'
        '    patch("%s.DesktopSession")\n' % SHELL_DOTTED
    )
    assert find_violations(src, ALLOWED) == []


def test_defined_names_covers_def_class_and_assignment_but_not_imports():
    src = (
        "import os\nfrom a import b\nX = 1\nY: int = 2\nT, U = 1, 2\n"
        "def f(): pass\nasync def g(): pass\nclass C: pass\n"
    )
    assert defined_names(src) == {"X", "Y", "T", "U", "f", "g", "C"}


def test_a_fixture_returning_an_alias_is_followed_in_the_same_file():
    src = (
        "import pytest\nimport importlib\n"
        "@pytest.fixture\ndef shell_module():\n"
        f"    import {SHELL_DOTTED} as m\n    return importlib.reload(m)\n"
        '\ndef test_x(monkeypatch, shell_module):\n    monkeypatch.setattr(shell_module, "X", 1)\n'
    )
    assert [n for _, n in find_violations(src, ALLOWED)] == ["X"]


def test_a_conftest_fixture_is_followed_from_another_file():
    conftest = (
        f"import pytest\nfrom {SHELL_PACKAGE} import shell\n"
        "@pytest.fixture\ndef the_shell():\n    yield shell\n"
    )
    fixtures = shell_fixtures(conftest)
    assert fixtures == {"the_shell"}
    src = 'def test_x(monkeypatch, the_shell):\n    monkeypatch.setattr(the_shell, "X", 1)\n'
    assert [n for _, n in find_violations(src, ALLOWED, fixtures)] == ["X"]


def test_a_module_that_is_not_shell_is_not_flagged():
    src = (
        "import pytest\n"
        "@pytest.fixture\ndef shell():\n    return object()\n"
        '\ndef test_x(monkeypatch, shell):\n    monkeypatch.setattr(shell, "X", 1)\n'
        "    shell.Y = 2\n"
        f'    from {SHELL_PACKAGE} import host\n    monkeypatch.setattr(host, "Z", 1)\n'
    )
    assert find_violations(src, ALLOWED) == []
