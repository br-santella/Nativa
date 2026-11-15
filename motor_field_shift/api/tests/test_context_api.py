"""/v1/contexto endpoint with the context and the area resolution mocked."""
from __future__ import annotations

import pytest


@pytest.fixture
def ctx(monkeypatch, fake):
    from field_shift import context

    calls = []
    monkeypatch.setattr(fake, "_resolver_area", lambda area: {"lat": -24.8, "lon": -53.5, **{"_area": area}}, raising=False)

    def build(lat, lon, sowing="01/02", cache_only=False):
        calls.append((lat, lon, sowing))
        return {"consultado_em": "x", "aviso": "informativo", "enso": {"disponivel": False, "motivo": "m"}}

    monkeypatch.setattr(context, "build", build)
    return calls


def test_context_get_field(client, ctx):
    r = client.get("/v1/contexto", params={"talhao_id": "72638", "semeadura_safrinha": "15/02"})
    assert r.status_code == 200 and r.json()["enso"]["disponivel"] is False
    assert ctx == [(-24.8, -53.5, "15/02")]


def test_context_post_point(client, ctx):
    r = client.post("/v1/contexto", json={"area": {"lat": -24.95, "lon": -53.45}})
    assert r.status_code == 200 and ctx[0][2] == "01/02"


def test_context_get_requires_one_shape(client, ctx):
    assert client.get("/v1/contexto").status_code == 422
    assert client.get("/v1/contexto", params={"lat": -24.9}).status_code == 422
