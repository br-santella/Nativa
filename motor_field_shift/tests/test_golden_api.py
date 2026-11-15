"""Golden tests: the public API must answer exactly as recorded before the English migration.

Record (only when a contract change is intended):  UPDATE_GOLDEN=1 uv run pytest tests/test_golden_api.py -m integracao
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(Path(__file__).parent))

from golden_requests import all_requests  # noqa: E402

GOLDEN = Path(__file__).parent / "golden"
VOLATILE_KEYS = {"cache_utilizado", "consultado_em", "versao"}

pytestmark = pytest.mark.integracao


def _scrub(obj):
    if isinstance(obj, dict):
        return {k: ("<volatile>" if k in VOLATILE_KEYS else _scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from field_shift_api.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _call(client, method, url, body, headers=None):
    r = client.request(method, url, json=body, headers=headers) if body is not None else client.request(method, url, headers=headers)
    return {"status": r.status_code, "body": _scrub(r.json())}


@pytest.mark.parametrize("name", sorted(all_requests()))
def test_golden(client, name):
    method, url, body = all_requests()[name]
    got = _call(client, method, url, body)
    path = GOLDEN / f"{name}.json"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        pytest.skip("golden updated")
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert got == expected
