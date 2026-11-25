"""Sentinel: each pytest-xdist worker has its own data directory (M37 F1 L2).

Workers inherit the controller's environment. `tests/conftest.py` gives every
worker a fresh `THE_ONE_DATA_DIR` containing its worker id, so the SQLite file,
encryption key and credential files are never shared between workers.
"""

from __future__ import annotations

import os

from the_one.config import settings


def test_worker_data_dir_contains_worker_id() -> None:
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    own = os.environ.get("_THE_ONE_PYTEST_OWN_DATA_DIR") == "1"
    if worker is not None and own:
        assert worker in str(settings.data_dir)
    else:
        # Serial run, or an explicit override that carries no marker: kept as set.
        assert str(settings.data_dir) == os.environ["THE_ONE_DATA_DIR"]
