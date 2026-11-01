"""Guard: a schema migration never imports live domain code (squawk 0295).

Schema history is append-only, so a later change to live code must not change what an
already-shipped migration does. ``the_one/db/schema.py`` may import only the modules in
``ALLOWED`` below. See ``the_one/agents.md`` "Project Conventions",
``frozen-migration-imports``.
"""

from __future__ import annotations

import ast
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "the_one" / "db" / "schema.py"

# Allowed ``the_one.*`` modules, each with the reason it is acceptable.
ALLOWED: dict[str, str] = {
    # Frozen data: the provider type table, not behaviour.
    "the_one.db._provider_types": "frozen data",
    # Known exception: the v48/v49 routine converters read the operator's zone and the
    # clock through the live module. Freezing them would mean copying the setting format
    # and system-zone detection, which is a design call, so the import stays until a
    # change to the ``time_zone`` setting format forces that call.
    "the_one.time_zones": "v48/v49 routine converters (known exception, see comment)",
}


def _imported_modules(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "the_one":
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.add("." * node.level + (node.module or ""))
            elif node.module and node.module.split(".")[0] == "the_one":
                if node.module == "the_one":
                    # ``from the_one import x`` imports the module ``the_one.x``.
                    found.update(f"the_one.{a.name}" for a in node.names)
                else:
                    found.add(node.module)
    return found


def test_schema_imports_only_allowed_the_one_modules() -> None:
    tree = ast.parse(SCHEMA.read_text(encoding="utf-8"))
    extra = sorted(_imported_modules(tree) - set(ALLOWED))
    assert not extra, (
        f"the_one/db/schema.py imports live code: {extra}. A migration must carry its own "
        "frozen copy instead (agents.md, frozen-migration-imports); add to ALLOWED only "
        "for frozen data, with the reason."
    )
