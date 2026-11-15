"""Testes contra o serviço real (precisam dos dados em data/). Rodar: uv run pytest -m integracao"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import SERVICO_REAL

RA = {"rotacao_atual": "soja__milho_safrinha"}
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
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, **RA})
    assert r.status_code == 200
    j = r.json()
    assert j["ranking"] and j["ranking"][0]["posicao"] == 1
    assert j["metodologia"]["formula"]


def _square(lat: float, lon: float, d: float = 0.003) -> dict:
    return {"type": "Polygon", "coordinates": [[[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d],
                                                [lon - d, lat + d], [lon - d, lat - d]]]}


@pytest.mark.parametrize("lat,lon", [(-23.55, -46.63), (-27.60, -48.55)])  # São Paulo (SP), Florianópolis (SC)
def test_fora_da_regiao(real, lat, lon):
    r = real.post("/v1/diagnostico", json={"area": {"lat": lat, "lon": lon}})
    assert r.status_code == 422 and r.json()["erro"] == "fora_da_regiao"


@pytest.mark.parametrize("lat,lon", [(-23.30, -51.30), (-25.10, -50.00)])  # soy fields near Londrina and Ponta Grossa
def test_pr_fora_do_oeste_tem_aviso_de_regiao(real, lat, lon):
    r = real.post("/v1/recomendacao", json={"area": {"geometry": _square(lat, lon)}, **RA})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ranking"]
    avisos = " ".join(j["avisos"])
    assert "fora do Oeste do Paraná" in avisos and "ADAPAR" in avisos and "custos" in avisos


def test_oeste_sem_aviso_de_regiao(real):
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, **RA})
    assert r.status_code == 200
    assert not any("fora do Oeste do Paraná" in a for a in r.json()["avisos"])


def test_notas_72638(real):
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, **RA, "semeadura_safrinha": "01/02"})
    rk = r.json()["ranking"]
    notas = {i.get("id_legado"): i["nota"] for i in rk if "id_legado" in i}  # as 6 rotações antigas (soja no verão)
    assert notas["milho_braquiaria"] == 0.764
    assert notas["milho_safrinha"] == 0.709 and notas["milheto_crotalaria"] == 0.759
    assert notas["aveia"] == 0.703 and notas["pousio"] == 0.555 and notas["trigo"] == 0.471
    assert rk[0]["margem"]["incremental_r_ha"] == 928 and rk[0]["margem"]["escala_S_r_ha"] == 1503
    assert rk[0]["id"] == "soja__milho_braquiaria" and rk[0]["card"]["por_que"].startswith("Em relação à atual (milho safrinha)")


def test_ponto_guaira(real):
    r = real.post("/v1/recomendacao", json={"area": {"lat": -24.20, "lon": -54.20}, **RA})
    assert r.status_code == 200, r.text


def test_atual_eliminada(real):
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, "rotacao_atual": "soja_safrinha"})
    assert r.status_code == 200
    a = r.json()["atual"]
    assert a["eliminada"] is True and a["nota"] is None and a["posicao"] is None and a["motivos"]


def test_pesos_zero_e_custo_milho(real):
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, **RA, "ajustes": {"custos": {"milho": 4000}}, "pesos": {"renda": 0, "solo": 0, "agua": 0, "pragas": 0, "risco": 0}})
    assert r.status_code == 200


def test_ajuste_chave_desconhecida_422(real):
    r = real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, **RA, "ajustes": {"custos": {"arroz": 1}}})
    assert r.status_code == 422


def test_recomendacao_dados_proprios(real):
    corpo = {
        "area": {"talhao_id": "72638"},
        **RA,
        "ajustes": {"produtividade": {"soja": 65, "milho": 110, "trigo": 50}},
        "analise_solo": {"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5, "cad_mm_cm": 1.4},
        "restricoes": {"culturas_excluidas": ["trigo"], "maquinas": {"plataforma_milho": True, "semeadora_consorcio": False}},
        "irrigacao": {"disponivel": True},
    }
    r = real.post("/v1/recomendacao", json=corpo)
    assert r.status_code == 200
    j = r.json()
    assert {"soja__soja_safrinha", "soja__trigo"} <= {e["id"] for e in j["eliminadas"]}
    assert j["diagnostico"]["solo"]["fonte"] == "análise de solo do produtor"
    top = {x["id"]: x for x in j["ranking"]}
    assert top["soja__milho_braquiaria"]["irrigacao"]["lamina_media_mm_ano"] > 0
    assert any("terceirizar" in a for a in top["soja__milho_braquiaria"]["card"]["avisos"])
    assert j["metodologia"]["ajustes_aplicados"]
    # entradas inválidas: Pydantic (422) e motor (400)
    assert real.post("/v1/recomendacao", json={**corpo, "analise_solo": {"argila_pct": 70, "areia_pct": 40}}).status_code == 422
    assert real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, **RA, "restricoes": {
        "culturas_excluidas": ["milho_safrinha", "milho_braquiaria", "trigo", "aveia", "milheto_crotalaria", "pousio"],
        "sem_comprador": ["milho"]}, "rotacoes": [{"verao": "soja", "segunda": "milho_safrinha"}]}).status_code == 200  # `rotacoes` só eliminadas: sem erro
    assert real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}, **RA, "restricoes": {
        "culturas_excluidas": ["milho_safrinha", "milho_braquiaria", "trigo", "aveia", "milheto_crotalaria", "pousio"],
        "sem_comprador": ["milho"]}}).status_code == 200  # os slugs antigos só valem p/ soja; sobram nabo, sorgo, feijão


def test_rotacoes_pedidas(real):
    corpo = {"area": {"talhao_id": "72638"}, "semeadura_safrinha": "01/03", "rotacao_atual": "soja__milho_safrinha",
             "rotacoes": [{"verao": "soja", "segunda": "milho_safrinha"}, {"verao": "soja", "segunda": "sorgo"},
                          {"verao": "milho_verao", "segunda": "aveia_nabo"}, {"verao": "milho_verao", "segunda": "milho_safrinha"},
                          {"verao": "milho_verao", "segunda": "soja_safrinha"}]}
    r = real.post("/v1/recomendacao", json=corpo)
    assert r.status_code == 200, r.text
    j = r.json()
    assert {x["id"] for x in j["agora"]["ranking"]} == {"soja__milho_safrinha", "soja__sorgo"}
    assert {x["id"] for x in j["proxima_safra"]["ranking"]} == {"milho_verao__aveia_nabo", "milho_verao__milho_safrinha"}
    assert [e["id"] for e in j["eliminadas"]] == ["milho_verao__soja_safrinha"] and j["eliminadas"][0]["motivos"]
    assert [e["id"] for e in j["proxima_safra"]["eliminadas"]] == ["milho_verao__soja_safrinha"] and not j["agora"]["eliminadas"]
    mm = next(x for x in j["proxima_safra"]["ranking"] if x["id"] == "milho_verao__milho_safrinha")
    assert any("cigarrinha" in t for t in mm["card"]["riscos"])
    for ruim in ([], [corpo["rotacoes"][0]] * 2, [{"verao": "soja", "segunda": "girassol"}]):
        assert real.post("/v1/recomendacao", json={**corpo, "rotacoes": ruim}).status_code == 422


def test_opcoes_culturas_e_combinacoes(real):
    o = real.get("/v1/opcoes").json()
    assert [c["id"] for c in o["culturas_verao"]] == ["soja", "milho_verao"]
    assert len(o["culturas_segunda"]) == 11 and len(o["combinacoes"]) == 22
    assert next(c for c in o["combinacoes"] if c["id"] == "soja__soja_safrinha")["valida"] is False


def test_soja_enchimento_graos_exemplo_principal(real):
    corpo = {"area": {"talhao_id": "72638"}, "rotacao_atual": "soja__milho_safrinha", "estagio_verao": "enchimento_graos",
             "data_referencia": "2026-12-01"}
    r = real.post("/v1/recomendacao", json=corpo)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["colheita_estimada"] == {"data": "02/01", "origem": "estagio"} and j["dias_ate_colheita"] == 32
    assert j["semeadura_2a"] == {"data": "15/01", "origem": "derivada"} and j["cultura_atual"]["id"] == "soja"
    assert j["ranking"] == j["agora"]["ranking"] and all(x["id"].startswith("soja__") for x in j["agora"]["ranking"])
    assert all(x["id"].startswith("milho_verao__") for x in j["proxima_safra"]["ranking"])
    top = j["agora"]["ranking"][0]
    assert top["ganho_vs_atual"]["soja_seguinte_sc"] == 2.0 and top["ganho_vs_atual"]["renda_2a_safra"]["origem"].startswith("dado")
    # 422 do contrato novo
    assert real.post("/v1/recomendacao", json={"area": {"talhao_id": "72638"}}).status_code == 422
    assert real.post("/v1/recomendacao", json={**corpo, "estagio_verao": "pendoamento"}).status_code == 422
    assert real.post("/v1/recomendacao", json={**corpo, "estagio_verao": "floracao", "semeadura_safrinha": "15/01"}).status_code == 422


def test_opcoes_estagios(real):
    soja = next(c for c in real.get("/v1/opcoes").json()["culturas_verao"] if c["id"] == "soja")
    assert soja["estagios"][3] == {"id": "enchimento_graos", "nome": "Enchimento de grãos (R5–R6)", "dias_ate_colheita": 32}
