"""Unit pins for packaging/windows/smoke.py (M32 F4 leg 3: the lifecycle dispatch-1 401).

The probe once sent ``f"Bearer {get_credential()}"``: ``str()`` of a credential is the redacted
repr, so the gate answered 401 for 60 s. These run on Linux with no server.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from the_one.api_credential import LocalApiCredential

SMOKE_PATH = Path(__file__).resolve().parent.parent / "packaging" / "windows" / "smoke.py"
SRC = SMOKE_PATH.read_text(encoding="utf-8")
_spec = importlib.util.spec_from_file_location("m32_smoke", SMOKE_PATH)
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


def test_bearer_header_uses_the_wire_form_not_the_redacted_repr():
    cred = LocalApiCredential.generate()
    header = smoke.bearer_header(cred)["Authorization"]
    assert header == f"Bearer {cred.encode()}"
    assert "redacted" not in header
    assert LocalApiCredential.parse(header.removeprefix("Bearer ")) is not None


def test_source_never_formats_a_credential_object_directly():
    assert not re.search(r"Bearer \{get_credential\(\)\}", SRC)
    assert "bearer_header(" in SRC


def test_describe_credential_shows_id_prefix_never_the_secret(tmp_path):
    cred = LocalApiCredential.generate()
    path = tmp_path / "api-credential"
    path.write_text(cred.encode())
    line = smoke.describe_credential(tmp_path, path, cred.encode())
    assert f"loc_{cred.identifier}" in line
    assert cred.secret not in line
    assert "exists=True" in line


def test_describe_credential_missing_file(tmp_path):
    line = smoke.describe_credential(tmp_path, tmp_path / "api-credential", None)
    assert "exists=False" in line and "n/a" in line


def test_port_comes_from_settings(monkeypatch):
    from the_one.config import settings

    monkeypatch.setattr(settings, "port", 8491)
    assert smoke._port() == 8491
    assert "PORT = 8484" not in SRC
