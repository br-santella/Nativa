"""Testes contra o serviço real (precisam dos dados em data/). Rodar: uv run pytest -m integracao"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import SERVICO_REAL

pytestmark = [
    pytest.mark.integracao,
    pytest.mark.skipif(not SERVICO_REAL, reason="serviço real ainda não existe"),
]


@pytest.fixture(scope="module")
def real():
    from field_shift_api.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_health(real):
    assert real.get("/health").json()["dados_carregados"] is True


def test_recomendacao_talhao_demo(real):
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}})
    assert r.status_code == 200
    j = r.json()
    assert j["ranking"] and j["ranking"][0]["posicao"] == 1
    assert j["metodologia"]["formula"]


def test_fora_da_regiao(real):
    r = real.post("/v1/diagnostico", json={"area": {"lat": -23.55, "lon": -46.63}})
    assert r.status_code == 422 and r.json()["erro"] == "fora_da_regiao"


def test_notas_72638(real):
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, "semeadura_safrinha": "01/02"})
    rk = r.json()["ranking"]
    notas = {i["id"]: i["nota"] for i in rk}
    assert notas["milho_braquiaria"] == 0.814
    assert notas["milho_safrinha"] == 0.757 and notas["milheto_crotalaria"] == 0.756
    assert notas["aveia"] == 0.698 and notas["pousio"] == 0.547 and notas["trigo"] == 0.466
    assert rk[0]["margem"]["incremental_r_ha"] == 1033 and rk[0]["margem"]["escala_S_r_ha"] == 1083
    assert rk[0]["card"]["por_que"].startswith("Em relação à atual (milho safrinha)")


def test_ponto_guaira(real):
    r = real.post("/v1/recomendacao", json={"area": {"lat": -24.20, "lon": -54.20}})
    assert r.status_code == 200, r.text


def test_atual_eliminada(real):
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, "rotacao_atual": "soja_safrinha"})
    assert r.status_code == 200
    a = r.json()["atual"]
    assert a["eliminada"] is True and a["nota"] is None and a["posicao"] is None and a["motivos"]


def test_pesos_zero_e_custo_milho(real):
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, "ajustes": {"custos": {"milho": 4000}}, "pesos": {"renda": 0, "solo": 0, "agua": 0, "pragas": 0, "risco": 0}})
    assert r.status_code == 200


def test_ajuste_chave_desconhecida_422(real):
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, "ajustes": {"custos": {"arroz": 1}}})
    assert r.status_code == 422
