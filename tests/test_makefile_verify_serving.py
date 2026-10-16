"""verify-serving derives its admin asset list from disk (squawks 0193, 0198)."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
JS_ROOT = ROOT / "the_one/interfaces/web/static/js/areas"


def test_asset_list_is_derived_not_literal():
    # A literal list names moved files; the loop must derive from disk instead.
    assert "providers-list.js" not in MAKEFILE
    assert re.search(r"for f in admin\.js \$\$\(cd \$\(ADMIN_JS_ROOT\) && find admin", MAKEFILE)


def test_derivation_yields_existing_files():
    m = re.search(r"\$\$\((cd \$\(ADMIN_JS_ROOT\) && find admin[^)]*)\)", MAKEFILE)
    assert m, "derivation command not found"
    cmd = m.group(1).replace("$(ADMIN_JS_ROOT)", str(JS_ROOT))
    out = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, check=True).stdout
    files = out.split()
    assert "admin/system-page.js" in files
    assert "admin/date-time-page.js" in files
    for f in ["admin.js", *files]:
        assert (JS_ROOT / f).is_file(), f
