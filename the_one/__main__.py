"""Enable ``python -m the_one <subcommand>`` (mirrors the ``the-one`` script).

Lets the frozen-runtime ``doctor`` diagnostic (and every other subcommand) be
invoked as ``python -m the_one doctor`` — the form Leg 4's CI packaged-smoke and
the host-native dev loop use before a frozen binary exists.
"""

from __future__ import annotations

from the_one.main import cli_entry

if __name__ == "__main__":
    cli_entry()
