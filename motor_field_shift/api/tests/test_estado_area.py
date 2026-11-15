"""Estado da área: `problemas_area` e fertilidade em `analise_solo` (ambos opcionais).

Unitários (sem dados): vocabulário, validação, classes, fórmula de calagem, API com serviço falso.
Integração (`uv run pytest -m integracao api/tests/test_estado_area.py`): motor real no talhão demo 72638.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import SERVICO_REAL
from field_shift.app import estado_area as EA
from field_shift.motor import servico as svc
from field_shift_api import schemas

AREA = {"talhao_id": "72638"}
RA = {"rotacao_atual": "soja__milho_safrinha"}
POBRE = dict(p_mg_dm3=2, k_cmolc_dm3=0.10, ca_cmolc_dm3=1.0, mg_cmolc_dm3=0.4, al_cmolc_dm3=1.5, v_pct=30, ctc_cmolc_dm3=9)
ESPERADO = {"milho_braquiaria": 0.814, "milho_safrinha": 0.757, "milheto_crotalaria": 0.756, "aveia": 0.698, "pousio": 0.547, "trigo": 0.466}


# --------------------------------------------------------------------------- vocabulário e validação
def test_vocabulario_yaml_schema_e_motor_coincidem():
    yml = Path(__file__).resolve().parents[3] / "catalog" / "vocabulario.yaml"
    voc = yaml.safe_load(yml.read_text(encoding="utf-8"))["problemas_area"]
    assert tuple(voc) == EA.PROBLEMAS == EA._PROBLEMAS_FALLBACK
    assert set(schemas.ProblemaArea.__args__) == set(EA.PROBLEMAS)
    assert set(EA.EFEITOS_PROBLEMAS) == set(EA.PROBLEMAS)


def test_problemas_area_invalido_no_servico():
    for ruim in (["ferrugem"], "nematoide", [1], ["nematoide", None]):
        with pytest.raises(svc.EntradaInvalida):
            svc._normalizar_problemas_area(ruim)
    assert svc._normalizar_problemas_area(None) is None and svc._normalizar_problemas_area([]) is None
    assert svc._normalizar_problemas_area(["mofo_branco", "mofo_branco", "nematoide"]) == ["mofo_branco", "nematoide"]


@pytest.mark.parametrize("campo,valor", [("v_pct", 120), ("v_pct", -1), ("p_mg_dm3", 9999), ("al_cmolc_dm3", 99), ("k_cmolc_dm3", "x"), ("ctc_cmolc_dm3", 61)])
def test_fertilidade_fora_dos_limites_no_servico(campo, valor):
    with pytest.raises(svc.EntradaInvalida):
        svc._normalizar_analise_solo({"argila_pct": 50, "areia_pct": 20, campo: valor})


def test_analise_so_com_fertilidade_e_separacao():
    n = svc._normalizar_analise_solo({"p_mg_dm3": 4, "v_pct": 40})
    fis, fert = svc._separar_fertilidade(n)
    assert fis is None and fert["valores"] == {"p_mg_dm3": 4.0, "v_pct": 40.0}
    n = svc._normalizar_analise_solo({"argila_pct": 50, "areia_pct": 20, "p_mg_dm3": 4})
    fis, fert = svc._separar_fertilidade(n)
    assert "p_mg_dm3" not in fis and fis["argila_pct"] == 50 and fert["classes"] == {"p": "baixo"}
    assert svc._separar_fertilidade(svc._normalizar_analise_solo({"argila_pct": 50, "areia_pct": 20}))[1] is None
    with pytest.raises(svc.EntradaInvalida):
        svc._normalizar_analise_solo({"ph": 5.5})  # nem textura, nem CAD, nem fertilidade


# --------------------------------------------------------------------------- fertilidade (módulo puro)
def test_classes_e_v_derivada_sem_estimar():
    f = EA.preparar_fertilidade(POBRE)
    assert f["classes"] == {"p": "muito_baixo", "k": "baixo", "v": "muito_baixa", "al": "alto"}
    assert f["severidade_acidez"] == 2 and f["pk_baixo"] and f["pobre"] and f["ausentes"] == []
    d = EA.preparar_fertilidade(dict(ca_cmolc_dm3=2, mg_cmolc_dm3=1, k_cmolc_dm3=0.2, ctc_cmolc_dm3=8))
    assert abs(d["valores"]["v_pct"] - 40.0) < 1e-9 and "derivada" in d["v_origem"]
    p = EA.preparar_fertilidade({"p_mg_dm3": 20})  # só P: nada de V%, Al ou K inventados
    assert p["classes"] == {"p": "muito_alto"} and "v_pct" not in p["valores"] and p["severidade_acidez"] == 0 and not p["pobre"]
    assert EA.preparar_fertilidade({}) is None and EA.preparar_fertilidade(None) is None


def test_sem_estado_nada_muda():
    from field_shift.app import engine as E

    c = E.CATALOGO["Soja → trigo"]
    assert EA.custos(c, None) == [] and EA.ajuste(c, None) == dict(pragas=0.0, solo=0.0, efeitos=[])
    assert EA.ajustes_aplicados(None, False) == []
    assert EA.ajustes_aplicados({"problemas": [], "fert": None}, False) == []
    assert EA.card(c, None)["evidencias"] == []


def test_calagem_formula_e_custos():
    from field_shift.app import engine as E

    fert = EA.preparar_fertilidade(POBRE)
    estado = {"problemas": [], "fert": fert}
    nc = (70 - 30) / 100 * 9 / EA.PRNT  # 4,5 t/ha
    assert abs(EA._nc_t_ha(fert, 70) - nc) < 1e-9
    trigo = {i["chave"]: i for i in EA.custos(E.CATALOGO["Soja → trigo"], estado)}
    assert abs(trigo["calagem"]["custo"] - nc * EA.CALCARIO_R_T / EA.CALAGEM_ANOS) < 1e-6
    # P muito baixo (+40 kg P2O5) e K baixo (+30 kg K2O) acima da classe média embutida no CONAB
    assert abs(trigo["adubacao_pk"]["custo"] - (40 * EA.PRECO_P2O5_R_KG + 30 * EA.PRECO_K2O_R_KG)) < 1e-6
    # cobertura e pousio não levam calagem nem adubação P/K
    for n in ("Soja → nabo forrageiro (cobertura)", "Soja → pousio", "Soja → aveia (cobertura/palha)"):
        assert EA.custos(E.CATALOGO[n], estado) == []
    # sem V%/CTC não há calagem (nada estimado); solo rico dá economia de adubação
    so_p = EA.custos(E.CATALOGO["Soja → trigo"], {"fert": EA.preparar_fertilidade({"p_mg_dm3": 30}), "problemas": []})
    assert [i["chave"] for i in so_p] == ["adubacao_pk"] and so_p[0]["custo"] < 0
    # V% já acima da meta: sem calagem
    assert not any(i["chave"] == "calagem" for i in EA.custos(E.CATALOGO["Soja → trigo"], {"fert": EA.preparar_fertilidade(dict(v_pct=80, ctc_cmolc_dm3=9)), "problemas": []}))


# --------------------------------------------------------------------------- API (serviço falso)
def test_api_problemas_area_invalido_422(client, chamadas):
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "problemas_area": ["ferrugem"]})
    assert r.status_code == 422 and not chamadas
    assert client.post("/v1/recomendacao", json={"area": AREA, **RA, "problemas_area": "nematoide"}).status_code == 422


def test_api_repassa_problemas_e_fertilidade(client, chamadas):
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "problemas_area": ["mofo_branco"], "analise_solo": {"p_mg_dm3": 3, "v_pct": 40}})
    assert r.status_code == 200
    kw = chamadas[0][2]
    assert kw["problemas_area"] == ["mofo_branco"] and kw["analise_solo"] == {"p_mg_dm3": 3.0, "v_pct": 40.0}
    client.post("/v1/recomendacao", json={"area": AREA, **RA})
    assert chamadas[1][2]["problemas_area"] is None


def test_api_fertilidade_invalida_422(client, chamadas):
    for ruim in ({"v_pct": 120}, {"p_mg_dm3": -1}, {"ph": 5.5}, {"argila_pct": 50, "areia_pct": 20, "al_cmolc_dm3": 99}):
        r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "analise_solo": ruim})
        assert r.status_code == 422, ruim
    assert not chamadas


# --------------------------------------------------------------------------- motor real
real = pytest.mark.skipif(not SERVICO_REAL, reason="serviço real indisponível")


def _rec(**kw):
    return svc.recomendar(AREA, **RA, incluir_diagnostico=False, **kw)


def _rk(r):
    return {x["id"]: x for x in r["agora"]["ranking"] + r["proxima_safra"]["ranking"]}


@pytest.fixture(scope="module")
def base():
    return _rec()


@pytest.mark.integracao
@real
def test_regressao_sem_campos_ranking_inalterado(base):
    assert {x["id_legado"]: x["nota"] for x in base["agora"]["ranking"] if "id_legado" in x} == ESPERADO
    assert "problemas_area" not in base["entrada"] and "ajustes_aplicados" not in base["metodologia"]
    for x in _rk(base).values():
        lac = " ".join(x["card"]["lacunas"])
        assert "Fertilidade não considerada (não informada)" in lac and "Problemas da área" in lac and "não informados" in lac
        assert all("Fertilidade:" not in e for e in x["card"]["evidencias"])
        assert not any(i["cultura"] in ("Calagem",) for i in x["margem"]["itens"])
    # a análise de solo sem fertilidade também não a considera, e o ajuste aplicado diz isso
    r = _rec(analise_solo={"argila_pct": 60, "areia_pct": 15})
    assert "Fertilidade não considerada (não informada)." in r["metodologia"]["ajustes_aplicados"]
    assert {k: v["criterios"] for k, v in _rk(r).items() if k.startswith("soja__")}["soja__trigo"]["pragas"] == _rk(base)["soja__trigo"]["criterios"]["pragas"]


@pytest.mark.integracao
@real
def test_problemas_area_mudam_a_ordem_no_sentido_esperado(base):
    b = _rk(base)
    r = _rec(problemas_area=["mofo_branco"])
    x = _rk(r)
    assert x["soja__feijao_safrinha"]["criterios"]["pragas"] < b["soja__feijao_safrinha"]["criterios"]["pragas"]
    assert x["soja__feijao_safrinha"]["nota"] < b["soja__feijao_safrinha"]["nota"]
    assert x["soja__nabo_forrageiro"]["criterios"]["pragas"] < b["soja__nabo_forrageiro"]["criterios"]["pragas"]
    assert x["soja__milheto_crotalaria"]["criterios"]["pragas"] == pytest.approx(b["soja__milheto_crotalaria"]["criterios"]["pragas"] - 0.15)  # só a soja de verão
    pos = lambda rr, i: next(k for k, v in enumerate(sorted(_rk(rr).values(), key=lambda v: -v["nota"])) if v["id"] == i)  # noqa: E731
    assert pos(r, "soja__feijao_safrinha") >= pos(base, "soja__feijao_safrinha")
    assert r["entrada"]["problemas_area"] == ["mofo_branco"]
    assert "Fertilidade não considerada (não informada)." in r["metodologia"]["ajustes_aplicados"]
    assert any("mofo-branco" in e and "feijão" in e for e in x["soja__feijao_safrinha"]["card"]["evidencias"])
    assert any("Problemas da área considerados: mofo-branco" in l for l in x["soja__feijao_safrinha"]["card"]["lacunas"])

    n = _rk(_rec(problemas_area=["nematoide"]))  # soja de verão -0,15 em todas; crotalária/milheto +0,25 e braquiária +0,10 por cima
    assert n["soja__milheto_crotalaria"]["criterios"]["pragas"] == pytest.approx(b["soja__milheto_crotalaria"]["criterios"]["pragas"] + 0.10)
    assert n["soja__milho_braquiaria"]["criterios"]["pragas"] == pytest.approx(b["soja__milho_braquiaria"]["criterios"]["pragas"] - 0.05)
    assert n["soja__feijao_safrinha"]["criterios"]["pragas"] < b["soja__feijao_safrinha"]["criterios"]["pragas"]
    assert n["soja__milheto_crotalaria"]["criterios"]["pragas"] > n["soja__milho_safrinha"]["criterios"]["pragas"]

    mv = dict(rotacao_atual="milho_verao__milho_safrinha", estagio_verao="maturacao", data_referencia="2027-01-10", incluir_diagnostico=False)
    bm, cm = _rk(svc.recomendar(AREA, **mv)), _rk(svc.recomendar(AREA, problemas_area=["cigarrinha"], **mv))
    # milho sobre milho: −0,05 (verão) −0,05 (safrinha) −0,15 (milho sobre milho); milho verão + trigo: só −0,05
    assert cm["milho_verao__milho_safrinha"]["criterios"]["pragas"] == pytest.approx(bm["milho_verao__milho_safrinha"]["criterios"]["pragas"] - 0.25)
    assert cm["milho_verao__trigo"]["criterios"]["pragas"] == pytest.approx(bm["milho_verao__trigo"]["criterios"]["pragas"] - 0.05)
    c = _rk(_rec(problemas_area=["cigarrinha"]))
    assert c["soja__milho_safrinha"]["criterios"]["pragas"] == pytest.approx(b["soja__milho_safrinha"]["criterios"]["pragas"] - 0.05)
    assert c["soja__trigo"]["criterios"] == b["soja__trigo"]["criterios"]

    k = _rk(_rec(problemas_area=["compactacao"]))
    for i in ("soja__nabo_forrageiro", "soja__milho_braquiaria"):
        assert k[i]["criterios"]["solo"] > b[i]["criterios"]["solo"] and k[i]["criterios"]["pragas"] == b[i]["criterios"]["pragas"]
    assert k["soja__trigo"]["criterios"]["solo"] == b["soja__trigo"]["criterios"]["solo"]


@pytest.mark.integracao
@real
def test_fertilidade_pobre_e_acida(base):
    b = _rk(base)
    r = _rec(analise_solo=POBRE)
    x = _rk(r)
    for i in ("soja__trigo", "soja__milho_safrinha"):
        assert x[i]["criterios"]["solo"] < b[i]["criterios"]["solo"]
        assert x[i]["nota"] < b[i]["nota"]
        chaves = [it["cultura"] for it in x[i]["margem"]["itens"]]
        assert "Calagem" in chaves and any(c.startswith("Adubação P/K") for c in chaves)
        assert x[i]["margem"]["total_r_ha"] < b[i]["margem"]["total_r_ha"]
    for i in ("soja__nabo_forrageiro", "soja__aveia_nabo", "soja__milheto_crotalaria"):
        assert x[i]["criterios"]["solo"] > b[i]["criterios"]["solo"]
    # milho+braquiária: bônus de reciclagem (+0,08) menor que a penalidade de acidez (−0,07 a −0,14), mas só ela leva calagem; coberturas sem efeito
    assert x["soja__aveia"]["criterios"] == b["soja__aveia"]["criterios"] and x["soja__aveia"]["margem"]["total_r_ha"] == b["soja__aveia"]["margem"]["total_r_ha"]
    # ranking relativo: coberturas recicladoras sobem frente ao trigo, que desce
    assert x["soja__nabo_forrageiro"]["nota"] > b["soja__nabo_forrageiro"]["nota"]
    assert x["soja__trigo"]["nota"] < b["soja__trigo"]["nota"]
    assert "Problemas da área não informados: não considerados." in r["metodologia"]["ajustes_aplicados"]
    assert any("Fertilidade informada" in a for a in r["metodologia"]["ajustes_aplicados"])
    assert all("Fertilidade não considerada" not in " ".join(v["card"]["lacunas"]) for v in x.values())
    assert any("Calagem" in e or "calagem" in e for e in x["soja__trigo"]["card"]["evidencias"])
    assert r["entrada"]["analise_solo"]["v_pct"] == 30 and "problemas_area" not in r["entrada"]


@pytest.mark.integracao
@real
def test_fertilidade_parcial_e_diagnostico(base):
    r = _rec(analise_solo={"p_mg_dm3": 2})  # só P: sem calagem (falta V% e CTC), sem penalidade de acidez
    x = _rk(r)["soja__trigo"]
    assert [i["cultura"] for i in x["margem"]["itens"]].count("Calagem") == 0
    lac = " ".join(x["card"]["lacunas"])
    assert "Calagem não calculada" in lac and "Fertilidade parcial" in lac
    assert x["criterios"]["solo"] == _rk(base)["soja__trigo"]["criterios"]["solo"]
    d = svc.diagnosticar(AREA, analise_solo=POBRE)
    assert d["fertilidade"]["classes"]["al"] == "alto" and d["solo"]["fonte"] != "análise de solo do produtor"
    assert "fertilidade" not in svc.diagnosticar(AREA)


@pytest.mark.integracao
@real
def test_valores_invalidos_no_motor_real():
    with pytest.raises(svc.EntradaInvalida):
        _rec(problemas_area=["ferrugem"])
    with pytest.raises(svc.EntradaInvalida):
        _rec(analise_solo={"v_pct": 150})
