from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from field_shift.motor import servico as svc

POLI = {
    "type": "Polygon",
    "coordinates": [[[-53.46, -24.96], [-53.45, -24.96], [-53.45, -24.95], [-53.46, -24.95], [-53.46, -24.96]]],
}


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["dados_carregados"] is True


def test_health_degradado_se_aquecer_falha(falso, monkeypatch):
    from field_shift_api.main import app

    def boom():
        raise RuntimeError("sem dados")

    monkeypatch.setattr(svc, "aquecer", boom)
    with TestClient(app) as c:
        j = c.get("/health").json()
    assert j["status"] == "degradado" and "sem dados" in j["detalhe"]


def test_opcoes_e_talhoes(client):
    assert client.get("/v1/opcoes").json()["semeadura_padrao"] == "01/02"
    assert client.get("/v1/talhoes/demo").json()[0]["talhao_id"] == "72638"


def test_cors(client):
    r = client.get("/health", headers={"Origin": "http://x.com"})
    assert r.headers["access-control-allow-origin"] == "*"


def test_diagnostico_talhao(client, chamadas):
    r = client.post("/v1/diagnostico", json={"area": {"talhao_id": "72638"}})
    assert r.status_code == 200
    j = r.json()
    assert j["area"]["municipio"]["nome"] == "Cascavel"
    assert j["clima"]["geada_por_semeadura"][0]["semeadura"] == "01/02"
    assert chamadas[0][1] == {"talhao_id": "72638"}
    assert chamadas[0][2]["semeadura_safrinha"] == "01/02"


def test_recomendacao_formato(client, chamadas):
    corpo = {
        "area": {"geometry": POLI},
        "semeadura_safrinha": "15/02",
        "pesos": {"renda": 8, "risco": 0},
        "rotacao_atual": "trigo",
        "ajustes": {"precos": {"soja": 120}, "linha_custo": "cot"},
        "n_alternativas": 2,
        "incluir_diagnostico": False,
    }
    r = client.post("/v1/recomendacao", json=corpo)
    assert r.status_code == 200
    j = r.json()
    item = j["ranking"][0]
    assert item["id"] == "milho_safrinha" and item["card"]["por_que"] == "x"
    assert item["margem"]["itens"][0]["cultura"] == "milho"
    assert j["eliminadas"][0]["motivos"] == ["soja sobre soja"]
    assert j["metodologia"]["versao"] == "0.1"
    _, area, kw = chamadas[0]
    assert area == {"geometry": POLI}
    assert kw["pesos"] == {"renda": 8.0, "risco": 0.0}
    assert kw["rotacao_atual"] == "trigo"
    assert kw["ajustes"] == {"precos": {"soja": 120.0}, "linha_custo": "cot"}
    assert kw["n_alternativas"] == 2 and kw["incluir_diagnostico"] is False


def test_recomendacao_padroes(client, chamadas):
    client.post("/v1/recomendacao", json={"area": {"lat": -24.9, "lon": -53.4}})
    _, area, kw = chamadas[0]
    assert area == {"lat": -24.9, "lon": -53.4}
    assert kw["pesos"] is None and kw["ajustes"] is None
    assert kw["n_alternativas"] == 3 and kw["incluir_diagnostico"] is True


def test_clima_atalho(client, chamadas):
    r = client.get("/v1/clima", params={"lat": -24.9, "lon": -53.4, "semeadura_safrinha": "15/03"})
    assert r.status_code == 200 and r.json()["fonte"] == "NASA POWER"
    assert chamadas[0][1] == {"lat": -24.9, "lon": -53.4}
    assert chamadas[0][2]["semeadura_safrinha"] == "15/03"


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"area": {}},
        {"area": {"talhao_id": "1", "lat": 1, "lon": 2}},
        {"area": {"lat": -24.9}},
        {"area": {"talhao_id": "1", "geometry": POLI}},
        {"area": {"talhao_id": "1"}, "semeadura_safrinha": "10/02"},
        {"area": {"talhao_id": "1"}, "pesos": {"renda": 11}},
        {"area": {"talhao_id": "1"}, "pesos": {"renda": -1}},
        {"area": {"talhao_id": "1"}, "pesos": {"outro": 1}},
        {"area": {"talhao_id": "1"}, "rotacao_atual": "arroz"},
        {"area": {"talhao_id": "1"}, "n_alternativas": 0},
        {"area": {"talhao_id": "1"}, "n_alternativas": 7},
        {"area": {"talhao_id": "1"}, "ajustes": {"linha_custo": "xx"}},
        {"area": {"talhao_id": "1"}, "ajustes": {"precos": {"arroz": 1}}},
        {"area": {"talhao_id": "1"}, "ajustes": {"custos": {"arroz": 1}}},
        {"area": {"talhao_id": "1"}, "ajustes": {"precos": {"soja": -1}}},
    ],
)
def test_validacao_422(client, corpo):
    assert client.post("/v1/recomendacao", json=corpo).status_code == 422


def test_validacao_diagnostico_e_clima(client):
    assert client.post("/v1/diagnostico", json={"area": {"talhao_id": "1"}, "semeadura_safrinha": "x"}).status_code == 422
    assert client.get("/v1/clima", params={"lat": 100, "lon": 0}).status_code == 422
    assert client.get("/v1/clima", params={"lat": 1}).status_code == 422
    assert client.get("/v1/clima", params={"lat": 1, "lon": 2, "semeadura_safrinha": "x"}).status_code == 422


@pytest.mark.parametrize(
    "rota,metodo,corpo",
    [
        ("/v1/diagnostico", "post", {"area": {"talhao_id": "1"}}),
        ("/v1/recomendacao", "post", {"area": {"talhao_id": "1"}}),
        ("/v1/clima?lat=-24.9&lon=-53.4", "get", None),
    ],
)
def test_mapeamento_erros(client, falso, monkeypatch, rota, metodo, corpo):
    for exc, status, codigo in [
        (svc.ForaDaRegiao("fora"), 422, "fora_da_regiao"),
        (svc.EntradaInvalida("ruim"), 400, "entrada_invalida"),
        (RuntimeError("segredo interno"), 500, "interno"),
    ]:
        def levanta(*a, _e=exc, **k):
            raise _e

        monkeypatch.setattr(svc, "diagnosticar", levanta)
        monkeypatch.setattr(svc, "recomendar", levanta)
        r = client.post(rota, json=corpo) if metodo == "post" else client.get(rota)
        assert r.status_code == status
        j = r.json()
        assert j["erro"] == codigo
        if codigo == "interno":
            assert "segredo" not in r.text and "Traceback" not in r.text
        else:
            assert j["mensagem"] in ("fora", "ruim")


def test_openapi_exemplos(client):
    j = client.get("/openapi.json").json()
    assert j["info"]["version"] == "0.1.0"
    assert "Oeste do Paraná" in j["info"]["description"]
    exs = j["components"]["schemas"]["RecomendacaoIn"]["examples"]
    assert exs[0]["area"]["talhao_id"] == "72638"
    assert "geometry" in exs[1]["area"]
