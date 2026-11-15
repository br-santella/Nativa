"""Golden tests: the public API must answer exactly as recorded before the English migration.

pt-BR (default): tests/golden/*.json, recorded from the code before the migration; must never change by accident.
English (`?lang=en`): tests/golden/en/*.json, plus checks that both languages have the same shape, ids and numbers.

Record (only when a contract change is intended):  UPDATE_GOLDEN=1 uv run pytest tests/test_golden_api.py -m integration
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
GOLDEN_EN = GOLDEN / "en"
VOLATILE_KEYS = {"cache_utilizado", "consultado_em", "versao"}

pytestmark = pytest.mark.integration


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


def test_openapi_unchanged(client):
    """The OpenAPI document (paths, operationIds, schema names and fields) is part of the public contract."""
    got = client.app.openapi()
    got = json.loads(json.dumps(got))
    got["info"].pop("version", None)
    path = GOLDEN / "openapi.json"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        pytest.skip("golden updated")
    assert got == json.loads(path.read_text(encoding="utf-8"))


def _with_lang(url: str, lang: str) -> str:
    return f"{url}{'&' if '?' in url else '?'}lang={lang}"


def _shape_diff(en, pt, key=None, path="") -> list[str]:
    """Where the English response differs from the pt-BR one in something other than translatable text: keys, list
    lengths, numbers, booleans, ids/enums (whole-value codes and enum keys) must be identical."""
    from field_shift.i18n import _CODE, _CODE_KEYS, _DISPLAY_KEYS

    if isinstance(pt, dict) and isinstance(en, dict):
        if en.keys() != pt.keys():
            return [f"{path}: keys {sorted(en.keys() ^ pt.keys())}"]
        return [d for k in pt for d in _shape_diff(en[k], pt[k], k, f"{path}.{k}")]
    if isinstance(pt, list) and isinstance(en, list):
        if len(en) != len(pt):
            return [f"{path}: {len(en)} items vs {len(pt)}"]
        return [d for i, (a, b) in enumerate(zip(en, pt)) for d in _shape_diff(a, b, key, f"{path}[{i}]")]
    if isinstance(pt, str) and isinstance(en, str):
        translatable = key in _DISPLAY_KEYS or (not _CODE.fullmatch(pt) and key not in _CODE_KEYS and key != "loc")
        return [] if en == pt or translatable else [f"{path}: code {pt!r} became {en!r}"]
    return [] if en == pt else [f"{path}: {pt!r} became {en!r}"]


@pytest.mark.parametrize("name", sorted(all_requests()))
def test_golden_en(client, name):
    """English response: recorded snapshot, same status and same shape/ids/numbers as the pt-BR one."""
    method, url, body = all_requests()[name]
    got = _call(client, method, _with_lang(url, "en"), body)
    path = GOLDEN_EN / f"{name}.json"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_EN.mkdir(exist_ok=True)
        path.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        pytest.skip("golden updated")
    assert got == json.loads(path.read_text(encoding="utf-8"))
    pt = json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert got["status"] == pt["status"]
    assert not _shape_diff(got["body"], pt["body"])


@pytest.mark.parametrize(("headers", "query", "expected"), [
    ({}, "", "pt-BR"),
    ({"Accept-Language": "en-US,en;q=0.9"}, "", "en"),
    ({"Accept-Language": "fr-FR,en;q=0.5,pt;q=0.8"}, "", "pt-BR"),
    ({"Accept-Language": "en"}, "?lang=pt-BR", "pt-BR"),
    ({}, "?lang=en", "en"),
    ({}, "?lang=xx", "pt-BR"),
])
def test_language_resolution(client, headers, query, expected):
    """`lang` > Accept-Language > pt-BR, announced in Content-Language; pt-BR is byte-identical to no preference."""
    r = client.get(f"/v1/opcoes{query}", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-language"] == expected
    default = client.get("/v1/opcoes").json()
    if expected == "pt-BR":
        assert r.json() == default
    else:
        assert r.json() != default and not _shape_diff(r.json(), default)


def test_openapi_not_translated(client):
    """The OpenAPI schema stays in Portuguese whatever the requested language."""
    assert client.get("/openapi.json?lang=en").json() == client.get("/openapi.json").json()
