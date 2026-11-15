from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from field_shift.core import service as svc

RA = {"rotacao_atual": "soja__milho_safrinha"}
POLY = {
    "type": "Polygon",
    "coordinates": [[[-53.46, -24.96], [-53.45, -24.96], [-53.45, -24.95], [-53.46, -24.95], [-53.46, -24.96]]],
}


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["dados_carregados"] is True


def test_health_degraded_if_warm_up_fails(fake, monkeypatch):
    from field_shift_api.main import app

    def boom():
        raise RuntimeError("sem dados")

    monkeypatch.setattr(svc, "warm_up", boom)
    with TestClient(app) as c:
        j = c.get("/health").json()
    assert j["status"] == "degradado" and "sem dados" in j["detalhe"]


def test_options_and_fields(client):
    assert client.get("/v1/opcoes").json()["semeadura_padrao"] == "01/02"
    assert client.get("/v1/talhoes/demo").json()[0]["talhao_id"] == "72638"


def test_cors(client):
    r = client.get("/health", headers={"Origin": "http://x.com"})
    assert r.headers["access-control-allow-origin"] == "*"


def test_diagnosis_field(client, calls):
    r = client.post("/v1/diagnostico", json={"area": {"talhao_id": "72638"}})
    assert r.status_code == 200
    j = r.json()
    assert j["area"]["municipio"]["nome"] == "Cascavel"
    assert j["clima"]["geada_por_semeadura"][0]["semeadura"] == "01/02"
    assert calls[0][1] == {"talhao_id": "72638"}
    assert calls[0][2]["sowing_second"] == "01/02"


def test_recommendation_format(client, calls):
    body = {
        "area": {"geometry": POLY},
        "semeadura_safrinha": "15/02",
        "pesos": {"renda": 8, "risco": 0},
        "rotacao_atual": "trigo",
        "ajustes": {"precos": {"soja": 120}, "linha_custo": "cot"},
        "n_alternativas": 2,
        "incluir_diagnostico": False,
    }
    r = client.post("/v1/recomendacao", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["agora"]["ranking"] == j["ranking"] and j["colheita_estimada"]["origem"] == "estagio"
    assert j["proxima_safra"]["ranking"][0]["ganho_vs_atual"]["comparado_com"] == "soja__milho_safrinha"
    item = j["ranking"][0]
    assert item["id"] == "soja__milho_safrinha" and item["id_legado"] == "milho_safrinha" and item["card"]["por_que"] == "x"
    assert item["margem"]["itens"][0]["cultura"] == "milho"
    assert j["eliminadas"][0]["motivos"] == ["soja sobre soja"]
    assert j["metodologia"]["versao"] == "0.1"
    _, area, kw = calls[0]
    assert area == {"geometry": POLY}
    assert kw["pesos"] == {"renda": 8.0, "risco": 0.0}
    assert kw["current_rotation"] == "trigo"
    assert kw["adjustments"] == {"precos": {"soja": 120.0}, "linha_custo": "cot"}
    assert kw["n_alternatives"] == 2 and kw["include_diagnosis"] is False


def test_recommendation_defaults(client, calls):
    client.post("/v1/recomendacao", json={"area": {"lat": -24.9, "lon": -53.4}, **RA})
    _, area, kw = calls[0]
    assert area == {"lat": -24.9, "lon": -53.4}
    assert kw["pesos"] is None and kw["adjustments"] is None
    assert kw["sowing_second"] is None and kw["summer_stage"] is None and kw["expected_harvest"] is None
    assert kw["reference_date"] is None
    assert kw["n_alternatives"] == 3 and kw["include_diagnosis"] is True


def test_recommendation_own_data(client, calls):
    body = {
        "area": {"talhao_id": "72638"},
        **RA,
        "ajustes": {"produtividade": {"soja": 65, "milho": 110, "trigo": 50}},
        "analise_solo": {"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5, "cad_mm_cm": 1.4},
        "restricoes": {
            "culturas_excluidas": ["trigo"],
            "maquinas": {"plataforma_milho": True, "semeadora_consorcio": False},
            "sem_comprador": ["aveia_grao"],
        },
        "irrigacao": {"disponivel": True, "custo_r_mm_ha": 4.5},
    }
    assert client.post("/v1/recomendacao", json=body).status_code == 200
    _, _, kw = calls[0]
    assert kw["adjustments"] == {"produtividade": {"soja": 65.0, "milho": 110.0, "trigo": 50.0}}
    assert kw["soil_analysis"] == {"argila_pct": 65.0, "areia_pct": 10.0, "materia_organica_pct": 3.5, "cad_mm_cm": 1.4}
    assert kw["constraints"] == body["restricoes"]
    assert kw["irrigation"] == {"disponivel": True, "custo_r_mm_ha": 4.5}
    # sem as entradas novas, chegam None
    client.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, **RA})
    kw = calls[1][2]
    assert kw["soil_analysis"] is None and kw["constraints"] is None and kw["irrigation"] is None


def test_diagnosis_with_soil_analysis(client, calls):
    r = client.post("/v1/diagnostico", json={"area": {"talhao_id": "72638"}, "analise_solo": {"cad_mm_cm": 1.2}})
    assert r.status_code == 200 and calls[0][2]["soil_analysis"] == {"cad_mm_cm": 1.2}


def test_climate_shortcut(client, calls):
    r = client.get("/v1/clima", params={"lat": -24.9, "lon": -53.4, "semeadura_safrinha": "15/03"})
    assert r.status_code == 200 and r.json()["fonte"] == "NASA POWER"
    assert calls[0][1] == {"lat": -24.9, "lon": -53.4}
    assert calls[0][2]["sowing_second"] == "15/03"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"area": {}},
        {"area": {"talhao_id": "1", "lat": 1, "lon": 2}},
        {"area": {"lat": -24.9}},
        {"area": {"talhao_id": "1", "geometry": POLY}},
        {"area": {"talhao_id": "1"}, **RA, "semeadura_safrinha": "10/02"},
        {"area": {"talhao_id": "1"}},  # rotacao_atual é obrigatória
        {"area": {"talhao_id": "1"}, **RA, "estagio_verao": "pendoamento"},  # estágio de milho com verão soja
        {"area": {"talhao_id": "1"}, **RA, "estagio_verao": "colheita"},
        {"area": {"talhao_id": "1"}, "rotacao_atual": "milho_verao__aveia", "estagio_verao": "enchimento_graos"},
        {"area": {"talhao_id": "1"}, **RA, "colheita_prevista": "2026-01-10"},
        {"area": {"talhao_id": "1"}, **RA, "colheita_prevista": "31/02"},
        {"area": {"talhao_id": "1"}, **RA, "data_referencia": "ontem"},
        {"area": {"talhao_id": "1"}, **RA, "estagio_verao": "enchimento_graos", "data_referencia": "2027-01-20", "semeadura_safrinha": "15/01"},
        {"area": {"talhao_id": "1"}, **RA, "colheita_prevista": "20/02", "semeadura_safrinha": "01/02"},
        {"area": {"talhao_id": "1"}, **RA, "pesos": {"renda": 11}},
        {"area": {"talhao_id": "1"}, **RA, "pesos": {"renda": -1}},
        {"area": {"talhao_id": "1"}, **RA, "pesos": {"outro": 1}},
        {"area": {"talhao_id": "1"}, **RA, "rotacao_atual": "arroz"},
        {"area": {"talhao_id": "1"}, **RA, "n_alternativas": 0},
        {"area": {"talhao_id": "1"}, **RA, "n_alternativas": 7},
        {"area": {"talhao_id": "1"}, **RA, "ajustes": {"linha_custo": "xx"}},
        {"area": {"talhao_id": "1"}, **RA, "ajustes": {"precos": {"arroz": 1}}},
        {"area": {"talhao_id": "1"}, **RA, "ajustes": {"custos": {"arroz": 1}}},
        {"area": {"talhao_id": "1"}, **RA, "ajustes": {"precos": {"soja": -1}}},
        {"area": {"talhao_id": "1"}, **RA, "ajustes": {"produtividade": {"soja": 0}}},
        {"area": {"talhao_id": "1"}, **RA, "ajustes": {"produtividade": {"arroz": 50}}},
        {"area": {"talhao_id": "1"}, **RA, "analise_solo": {"argila_pct": 60, "areia_pct": 50}},
        {"area": {"talhao_id": "1"}, **RA, "analise_solo": {"argila_pct": 60}},
        {"area": {"talhao_id": "1"}, **RA, "analise_solo": {"ph": 5}},
        {"area": {"talhao_id": "1"}, **RA, "analise_solo": {"argila_pct": 50, "areia_pct": 10, "ph": 9.5}},
        {"area": {"talhao_id": "1"}, **RA, "analise_solo": {"cad_mm_cm": 0.1}},
        {"area": {"talhao_id": "1"}, **RA, "analise_solo": {"cad_mm_cm": 4}},
        {"area": {"talhao_id": "1"}, **RA, "analise_solo": {"argila_pct": 50, "areia_pct": 10, "materia_organica_pct": 2, "carbono_organico_g_kg": 10}},
        {"area": {"talhao_id": "1"}, **RA, "restricoes": {"culturas_excluidas": ["arroz"]}},
        {"area": {"talhao_id": "1"}, **RA, "restricoes": {"sem_comprador": ["soja"]}},
        {"area": {"talhao_id": "1"}, **RA, "restricoes": {"maquinas": {"trator": True}}},
        {"area": {"talhao_id": "1"}, **RA, "irrigacao": {}},
        {"area": {"talhao_id": "1"}, **RA, "irrigacao": {"disponivel": True, "lamina_max_mm_dia": 0}},
        {"area": {"talhao_id": "1"}, **RA, "irrigacao": {"disponivel": True, "custo_r_mm_ha": -2}},
    ],
)
def test_validation_422(client, body):
    assert client.post("/v1/recomendacao", json=body).status_code == 422


def test_validation_diagnosis_and_climate(client):
    assert client.post("/v1/diagnostico", json={"area": {"talhao_id": "1"}, "semeadura_safrinha": "x"}).status_code == 422
    assert client.get("/v1/clima", params={"lat": 100, "lon": 0}).status_code == 422
    assert client.get("/v1/clima", params={"lat": 1}).status_code == 422
    assert client.get("/v1/clima", params={"lat": 1, "lon": 2, "semeadura_safrinha": "x"}).status_code == 422


@pytest.mark.parametrize(
    "route,method,body",
    [
        ("/v1/diagnostico", "post", {"area": {"talhao_id": "1"}}),
        ("/v1/recomendacao", "post", {"area": {"talhao_id": "1"}, **RA}),
        ("/v1/clima?lat=-24.9&lon=-53.4", "get", None),
    ],
)
def test_error_mapping(client, fake, monkeypatch, route, method, body):
    for exc, status, code in [
        (svc.OutOfRegion("fora"), 422, "fora_da_regiao"),
        (svc.InvalidInput("ruim"), 400, "entrada_invalida"),
        (RuntimeError("segredo interno"), 500, "interno"),
    ]:
        def raise_(*a, _e=exc, **k):
            raise _e

        monkeypatch.setattr(svc, "diagnose", raise_)
        monkeypatch.setattr(svc, "recommend", raise_)
        r = client.post(route, json=body) if method == "post" else client.get(route)
        assert r.status_code == status
        j = r.json()
        assert j["erro"] == code
        if code == "interno":
            assert "segredo" not in r.text and "Traceback" not in r.text
        else:
            assert j["mensagem"] in ("fora", "ruim")


def test_openapi_examples(client):
    j = client.get("/openapi.json").json()
    assert j["info"]["version"] == "0.1.0"
    assert "Paraná inteiro" in j["info"]["description"]
    exs = j["components"]["schemas"]["RecomendacaoIn"]["examples"]
    assert exs[0]["area"]["talhao_id"] == "72638" and exs[0]["estagio_verao"] == "enchimento_graos"
    assert exs[0]["data_referencia"] == "2026-12-01"
    assert "rotacoes" in exs[1] and {"verao", "segunda"} == set(exs[1]["rotacoes"][0])
    assert exs[2]["colheita_prevista"] == "20/01"
    assert "geometry" in exs[3]["area"]
    assert "irrigacao" in exs[4] and "analise_solo" in exs[4] and "restricoes" in exs[4]
    assert all("rotacao_atual" in e for e in exs)
    assert "rotacao_atual" in j["components"]["schemas"]["RecomendacaoIn"]["required"]
    props = j["components"]["schemas"]["RecomendacaoIn"]["properties"]
    assert {"analise_solo", "restricoes", "irrigacao", "rotacoes", "estagio_verao", "colheita_prevista", "data_referencia"} <= set(props)
