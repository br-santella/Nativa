"""Field state: `problemas_area` and fertility in `analise_solo` (both optional).

Unit tests (no data): vocabulary, validation, P/K/V%/Al classes by clay band, liming formula, qualitative levels, API with a fake service.
Integration (`uv run pytest -m integration api/tests/test_field_state.py`): real engine on demo field 72638.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import REAL_SERVICE
from field_shift.app import field_state as EA
from field_shift.core import service as svc
from field_shift_api import schemas

AREA = {"talhao_id": "72638"}
RA = {"rotacao_atual": "soja__milho_safrinha"}
POOR = dict(p_mg_dm3=2, k_cmolc_dm3=0.10, ca_cmolc_dm3=1.0, mg_cmolc_dm3=0.4, al_cmolc_dm3=1.5, v_pct=30, ctc_cmolc_dm3=9)
EXPECTED = {"milho_braquiaria": 0.795, "milho_safrinha": 0.747, "milheto_crotalaria": 0.757, "aveia": 0.7, "pousio": 0.57, "trigo": 0.524}
X = EA.LEVEL_MAGNITUDE


def _cand_crops(nome):
    from field_shift.app import engine as E

    return E.CATALOG[nome]


def _delta(nome, problem, criterion):
    return EA.adjustment(_cand_crops(nome), {"problemas": [problem], "fert": None})[criterion]


# Vocabulary and validation
def test_vocabulary_yaml_schema_and_engine_match():
    yml = Path(__file__).resolve().parents[3] / "catalog" / "vocabulario.yaml"
    voc = yaml.safe_load(yml.read_text(encoding="utf-8"))["problemas_area"]
    assert tuple(voc) == EA.PROBLEMS == EA._PROBLEMS_FALLBACK
    assert set(schemas.AreaProblem.__args__) == set(EA.PROBLEMS)
    assert set(EA.PROBLEM_EFFECTS) == set(EA.PROBLEMS)


def test_invalid_area_problems_in_service():
    for bad in (["ferrugem"], "nematoide", [1], ["nematoide", None]):
        with pytest.raises(svc.InvalidInput):
            svc._normalize_area_problems(bad)
    assert svc._normalize_area_problems(None) is None and svc._normalize_area_problems([]) is None
    assert svc._normalize_area_problems(["mofo_branco", "mofo_branco", "nematoide"]) == ["mofo_branco", "nematoide"]


@pytest.mark.parametrize("field_name,valor", [("v_pct", 120), ("v_pct", -1), ("p_mg_dm3", 9999), ("al_cmolc_dm3", 99), ("k_cmolc_dm3", "x"), ("ctc_cmolc_dm3", 61)])
def test_fertility_out_of_bounds_in_service(field_name, valor):
    with pytest.raises(svc.InvalidInput):
        svc._normalize_soil_analysis({"argila_pct": 50, "areia_pct": 20, field_name: valor})


def test_analysis_with_fertility_only_and_split():
    n = svc._normalize_soil_analysis({"p_mg_dm3": 4, "v_pct": 40})
    phys, fert = svc._split_fertility(n)
    assert phys is None and fert["valores"] == {"p_mg_dm3": 4.0, "v_pct": 40.0}
    assert fert["argila_origem"].startswith("não informada")  # no clay: most demanding band
    n = svc._normalize_soil_analysis({"argila_pct": 50, "areia_pct": 20, "p_mg_dm3": 4})
    phys, fert = svc._split_fertility(n)
    assert "p_mg_dm3" not in phys and phys["argila_pct"] == 50 and fert["classes"] == {"p": "baixo"} and fert["argila_faixa_g_kg"] == ">400"
    assert svc._split_fertility(svc._normalize_soil_analysis({"argila_pct": 50, "areia_pct": 20}))[1] is None
    with pytest.raises(svc.InvalidInput):
        svc._normalize_soil_analysis({"ph": 5.5})  # no texture, no CAD, no fertility


# Fertility classes (Manual PR, by clay band)
@pytest.mark.parametrize("clay_pct,p,expected", [
    (20, 5, "muito_baixo"), (20, 6, "baixo"), (20, 12.5, "baixo"), (20, 13, "medio"), (20, 19, "alto"), (20, 24, "alto"), (20, 25, "muito_alto"),
    (20, 121, "condicao_evitar"),
    (30, 3, "muito_baixo"), (30, 4, "baixo"), (30, 9, "medio"), (30, 13, "alto"), (30, 19, "muito_alto"), (30, 91, "condicao_evitar"),
    (50, 2, "muito_baixo"), (50, 3, "baixo"), (50, 7, "medio"), (50, 10, "alto"), (50, 13, "muito_alto"), (50, 61, "condicao_evitar"),
])
def test_p_class_by_clay_band(clay_pct, p, expected):
    assert EA.prepare_fertility({"p_mg_dm3": p}, clay_pct)["classes"]["p"] == expected


def test_p_same_value_reads_differently_by_clay_and_defaults_to_most_demanding():
    # P = 7 mg/dm3: baixo in sandy (<250 g/kg), baixo in medium (250-400), medio in clayey (>400)
    assert [EA.prepare_fertility({"p_mg_dm3": 7}, a)["classes"]["p"] for a in (20, 30, 50)] == ["baixo", "baixo", "medio"]
    no_clay = EA.prepare_fertility({"p_mg_dm3": 7})
    assert no_clay["classes"]["p"] == "baixo" and no_clay["argila_faixa_g_kg"] == "<250" and no_clay["argila_origem"].startswith("não informada")
    # the clay band edges (g/kg): 250 and 400 belong to the middle band; > 400 to the clayey one
    assert [EA.clay_band(a)[0] for a in (24.9, 25, 40, 40.1)] == ["<250", "250-400", "250-400", ">400"]
    # the conservative band never reads P as higher than any other band
    order = ["muito_baixo", "baixo", "medio", "alto", "muito_alto", "condicao_evitar"]
    for p in range(0, 130):
        c = [order.index(EA._p_class(p, b)) for b in EA.P_CLAY_BANDS]
        assert order.index(EA._p_class(p, EA.CONSERVATIVE_CLAY_BAND)) == min(c)


@pytest.mark.parametrize("valor,expected", [(0.05, "muito_baixo"), (0.06, "baixo"), (0.12, "baixo"), (0.13, "medio"), (0.21, "medio"), (0.22, "alto"),
                                            (0.45, "alto"), (0.46, "muito_alto")])
def test_k_classes(valor, expected):
    assert EA.prepare_fertility({"k_cmolc_dm3": valor})["classes"]["k"] == expected


@pytest.mark.parametrize("field_name,valor,expected", [
    ("v_pct", 19, "muito_baixo"), ("v_pct", 21, "baixo"), ("v_pct", 35, "baixo"), ("v_pct", 36, "medio"), ("v_pct", 50, "medio"), ("v_pct", 51, "alto"),
    ("v_pct", 70, "alto"), ("v_pct", 75, "muito_alto"), ("v_pct", 95, "condicao_evitar"),
    ("al_cmolc_dm3", 0.2, "muito_baixo"), ("al_cmolc_dm3", 0.5, "baixo"), ("al_cmolc_dm3", 1.0, "medio"), ("al_cmolc_dm3", 2.0, "alto"), ("al_cmolc_dm3", 3.0, "muito_alto"),
])
def test_v_and_al_classes(field_name, valor, expected):
    key = "v" if field_name == "v_pct" else "al"
    assert EA.prepare_fertility({field_name: valor})["classes"][key] == expected


def test_classes_and_derived_v_without_estimating():
    f = EA.prepare_fertility(POOR, 55)
    assert f["classes"] == {"p": "muito_baixo", "k": "baixo", "v": "baixo", "al": "medio"}
    assert f["severidade_acidez"] == 2 and f["pk_baixo"] and f["pobre"] and f["ausentes"] == []
    d = EA.prepare_fertility(dict(ca_cmolc_dm3=2, mg_cmolc_dm3=1, k_cmolc_dm3=0.2, ctc_cmolc_dm3=8))
    assert abs(d["valores"]["v_pct"] - 40.0) < 1e-9 and "derivada" in d["v_origem"]
    p = EA.prepare_fertility({"p_mg_dm3": 30}, 50)  # only P: no V%, Al or K invented
    assert p["classes"] == {"p": "muito_alto"} and "v_pct" not in p["valores"] and p["severidade_acidez"] == 0 and not p["pobre"]
    assert EA.prepare_fertility({}) is None and EA.prepare_fertility(None) is None
    assert EA.prepare_fertility({"k_cmolc_dm3": 0.2})["argila_faixa_g_kg"] is None  # clay only matters for P


# Qualitative levels of the area problems
def test_levels_use_one_declared_scale_and_every_effect_has_a_read_source():
    assert EA.LEVEL_DELTA == {"favorece": X, "neutro": 0.0, "penaliza": -X}
    for cond, targets in EA.FERTILITY_EFFECTS.items():
        for target, e in targets.items():
            assert e["level"] in ("favorece", "penaliza") and e["sources"], (cond, target)
            assert all(EA.SOURCES[sid]["url"].startswith("https://") for sid in e["sources"])
    for (cond, target), why in EA.FERTILITY_NEUTRAL_NO_SOURCE.items():
        assert cond in EA.FERTILITY_EFFECTS and target not in EA.FERTILITY_EFFECTS[cond] and why
    for problem, targets in EA.PROBLEM_EFFECTS.items():
        for target, e in targets.items():
            assert e["level"] in EA.LEVEL_DELTA and e["criterion"] in ("pragas", "solo")
            if e["level"] != "neutro":
                assert e["sources"], (problem, target)  # a non-neutral cell requires a source
                for sid in e["sources"]:
                    ref = EA.SOURCES[sid]
                    assert ref["url"].startswith("https://") and ref["label"] and ref["title"]


def test_pair_without_source_is_neutral_and_listed():
    for (problem, target), reason in EA.NEUTRAL_NO_SOURCE.items():
        assert problem in EA.PROBLEMS and reason
        assert target not in EA.PROBLEM_EFFECTS[problem]  # never both an effect and "no source"
    # white mold x oat+radish and nematode x corn+brachiaria have no confirmed source: neutral, flagged in the card
    c = _cand_crops("Soja → aveia + nabo forrageiro (cobertura)")
    e = EA.adjustment(c, {"problemas": ["mofo_branco"], "fert": None})
    assert e["pragas"] == pytest.approx(-X)  # only the summer soybean; the radish mix itself is neutral
    assert not any("nabo" in x["motivo"] for x in e["efeitos"])
    assert any("sem fonte confirmada" in l and "aveia" in l for l in EA.card(c, {"problemas": ["mofo_branco"], "fert": None})["lacunas"])
    # a pair that is in neither table is neutral and silent
    assert _delta("Soja → trigo", "cigarrinha", "pragas") == 0.0 and _delta("Soja → trigo", "compactacao", "solo") == 0.0


def test_white_mold_levels():
    assert _delta("Soja → feijão safrinha", "mofo_branco", "pragas") == pytest.approx(-2 * X)  # summer soybean + beans, both hosts
    assert _delta("Soja → nabo forrageiro (cobertura)", "mofo_branco", "pragas") == pytest.approx(-2 * X)  # radish is a host
    assert _delta("Soja → trigo", "mofo_branco", "pragas") == pytest.approx(-X)  # only the summer soybean; wheat is a grass, not a host
    assert _delta("Soja → soja safrinha", "mofo_branco", "pragas") == pytest.approx(-2 * X)
    assert _delta("Milho verão → trigo", "mofo_branco", "pragas") == 0.0  # grass after grass: no host in the rotation
    assert _delta("Milho verão → milho safrinha + braquiária", "mofo_branco", "pragas") == 0.0  # 1 year of brachiaria did not cut the sclerotia


def test_nematode_levels():
    assert _delta("Soja → feijão safrinha", "nematoide", "pragas") == pytest.approx(-2 * X)
    assert _delta("Soja → trigo", "nematoide", "pragas") == pytest.approx(-X)  # summer soybean only
    assert _delta("Soja → milheto/crotalária (cobertura)", "nematoide", "pragas") == pytest.approx(0.0)  # -X soybean + X crotalaria
    assert _delta("Milho verão → milheto/crotalária (cobertura)", "nematoide", "pragas") == pytest.approx(X)
    # species-dependent cells stay neutral (brachiaria and corn host P. brachyurus but not the others)
    assert _delta("Milho verão → milho safrinha + braquiária", "nematoide", "pragas") == 0.0
    c = _cand_crops("Soja → milho safrinha + braquiária")
    assert any("espécie" in l and "neutro" in l for l in EA.card(c, {"problemas": ["nematoide"], "fert": None})["lacunas"])


def test_leafhopper_and_compaction_levels():
    assert _delta("Milho verão → milho safrinha", "cigarrinha", "pragas") == pytest.approx(-X)  # corn on corn
    assert _delta("Milho verão → trigo", "cigarrinha", "pragas") == 0.0
    assert _delta("Soja → milho safrinha", "cigarrinha", "pragas") == 0.0  # single corn crop: no source for a penalty
    assert _delta("Soja → milho safrinha + braquiária", "compactacao", "solo") == pytest.approx(X)
    assert _delta("Soja → nabo forrageiro (cobertura)", "compactacao", "solo") == pytest.approx(X)
    assert _delta("Soja → aveia + nabo forrageiro (cobertura)", "compactacao", "solo") == 0.0  # tested: no gain
    assert _delta("Soja → trigo", "compactacao", "solo") == 0.0
    assert EA.adjustment(_cand_crops("Soja → nabo forrageiro (cobertura)"), {"problemas": ["compactacao"], "fert": None})["pragas"] == 0.0  # right criterion


def test_card_shows_source_and_caveat_of_each_applied_effect():
    c = _cand_crops("Soja → milheto/crotalária (cobertura)")
    ev = EA.card(c, {"problemas": ["nematoide"], "fert": None})["evidencias"]
    assert any("favorece" in e and "Inomoto & Asmus 2009" in e and "ressalva" in e and "spectabilis" in e for e in ev)
    assert any("penaliza" in e and "soja" in e for e in ev)
    gap = " ".join(EA.card(c, {"problemas": ["nematoide"], "fert": None})["lacunas"])
    assert "escolha de modelagem" in gap and "três níveis" in gap


# Fertility (pure module)
def test_no_state_changes_nothing():
    c = _cand_crops("Soja → trigo")
    assert EA.costs(c, None) == [] and EA.adjustment(c, None) == dict(pragas=0.0, solo=0.0, efeitos=[])
    assert EA.applied_adjustments(None, False) == []
    assert EA.applied_adjustments({"problemas": [], "fert": None}, False) == []
    assert EA.card(c, None)["evidencias"] == []


def test_liming_formula_and_reference_prnt():
    fert = EA.prepare_fertility(POOR, 55)
    assert abs(EA.PRNT - 1 / 1.3) < 1e-12  # CBPTT 2020: f = 100/PRNT = 1.3
    nc = (EA.V2["trigo"] - 30) / 100 * 9 / EA.PRNT  # t/ha
    assert abs(EA._nc_t_ha(fert, EA.V2["trigo"]) - nc) < 1e-9
    wheat = {i["chave"]: i for i in EA.costs(_cand_crops("Soja → trigo"), {"problemas": [], "fert": fert})}
    assert abs(wheat["calagem"]["custo"] - nc * EA.LIME_R_T / EA.LIMING_YEARS) < 1e-6
    assert "PR.0404" in wheat["calagem"]["detalhe"] and EA.ESTIMATE_SOURCE in wheat["calagem"]["detalhe"]
    # cap, no V%/CEC -> no liming, V% above the target -> no liming
    assert EA._nc_t_ha(EA.prepare_fertility(dict(v_pct=5, ctc_cmolc_dm3=30)), 60) == EA.NC_MAX_T_HA
    assert EA._nc_t_ha(EA.prepare_fertility({"p_mg_dm3": 3}), 60) is None
    assert not any(i["chave"] == "calagem" for i in EA.costs(_cand_crops("Soja → trigo"), {"fert": EA.prepare_fertility(dict(v_pct=80, ctc_cmolc_dm3=9)), "problemas": []}))


def test_corn_wheat_and_unsourced_fertilizer_costs():
    fert = EA.prepare_fertility(POOR, 55)  # P muito baixo, K baixo
    state = {"problemas": [], "fert": fert}
    # corn (Manual PR 2017 tables, yield < 8 t/ha, midpoints): P muito baixo 120 vs medio 80 = +40; K baixo 90 vs medio 55 = +35
    corn = {i["chave"]: i for i in EA.costs(_cand_crops("Soja → milho safrinha"), state)}
    assert abs(corn["adubacao_pk"]["custo"] - (40 * EA.P2O5_PRICE_R_KG + 35 * EA.K2O_PRICE_R_KG)) < 1e-6
    assert "Manual PR 2017" in corn["adubacao_pk"]["detalhe"] and "CNA/Cepea" in corn["adubacao_pk"]["detalhe"]
    # wheat (CBPTT 2020, by value): P 2 (< 5) -> 75 vs 50 = +25; K 0.10 (0.10-0.30) -> 50 vs 50 = 0
    wheat = {i["chave"]: i for i in EA.costs(_cand_crops("Soja → trigo"), state)}
    assert abs(wheat["adubacao_pk"]["custo"] - 25 * EA.P2O5_PRICE_R_KG) < 1e-6 and "CBPTT 2020" in wheat["adubacao_pk"]["detalhe"]
    # beans/sorghum: no confirmed source for the doses, and the cost item says so
    beans = {i["chave"]: i for i in EA.costs(_cand_crops("Soja → feijão safrinha"), state)}
    assert "sem fonte confirmada" in beans["adubacao_pk"]["detalhe"] and "Calagem" == beans["calagem"]["rotulo"]
    sorghum = {i["chave"]: i for i in EA.costs(_cand_crops("Soja → sorgo"), state)}
    assert abs(sorghum["adubacao_pk"]["custo"] - 0.6 * (40 * EA.P2O5_PRICE_R_KG + 30 * EA.K2O_PRICE_R_KG)) < 1e-6
    # covers and fallow carry the same liming as a grain crop (area-level need) but no P/K fertilizer (no dose model)
    for n in ("Soja → nabo forrageiro (cobertura)", "Soja → pousio", "Soja → aveia (cobertura/palha)"):
        items = EA.costs(_cand_crops(n), state)
        assert [i["chave"] for i in items] == ["calagem"]
        assert items[0]["custo"] == pytest.approx(wheat["calagem"]["custo"])  # same V2 -> same liming as wheat
        assert "necessidade da área" in items[0]["detalhe"] and "validar com agrônomo" in items[0]["detalhe"]
    # without V%/CEC nothing is estimated for covers either
    assert EA.costs(_cand_crops("Soja → pousio"), {"problemas": [], "fert": EA.prepare_fertility({"p_mg_dm3": 3}, 50)}) == []
    # no V%/CEC -> no liming; rich soil -> saving; "condição a evitar" -> no P fertilizer
    so_p = EA.costs(_cand_crops("Soja → trigo"), {"fert": EA.prepare_fertility({"p_mg_dm3": 30}, 50), "problemas": []})
    assert [i["chave"] for i in so_p] == ["adubacao_pk"] and so_p[0]["custo"] < 0
    avoid = EA.costs(_cand_crops("Soja → milho safrinha"), {"fert": EA.prepare_fertility({"p_mg_dm3": 80}, 50), "problemas": []})
    assert abs(avoid[0]["custo"] - (0 - 80) * EA.P2O5_PRICE_R_KG) < 1e-6
    # published ranges are respected: the midpoint of each corn cell lies inside the Manual's range
    assert 110 <= EA.DOSE_P2O5_CORN["muito_baixo"] <= 130 and 70 <= EA.DOSE_K2O_CORN["baixo"] <= 110 and 40 <= EA.DOSE_K2O_CORN["medio"] <= 70


def test_unsourced_constants_are_declared_in_the_card():
    fert = EA.prepare_fertility(POOR)  # no clay informed
    gap = " ".join(EA.card(_cand_crops("Soja → feijão safrinha"), {"problemas": [], "fert": fert})["lacunas"])
    assert "Argila não informada" in gap and "Preço do calcário" in gap and "sem fonte confirmada" in gap


# API (fake service)
def test_api_invalid_area_problems_returns_422(client, calls):
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "problemas_area": ["ferrugem"]})
    assert r.status_code == 422 and not calls
    assert client.post("/v1/recomendacao", json={"area": AREA, **RA, "problemas_area": "nematoide"}).status_code == 422


def test_api_forwards_problems_and_fertility(client, calls):
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "problemas_area": ["mofo_branco"], "analise_solo": {"p_mg_dm3": 3, "v_pct": 40}})
    assert r.status_code == 200
    kw = calls[0][2]
    assert kw["area_problems"] == ["mofo_branco"] and kw["soil_analysis"] == {"p_mg_dm3": 3.0, "v_pct": 40.0}
    client.post("/v1/recomendacao", json={"area": AREA, **RA})
    assert calls[1][2]["area_problems"] is None


def test_api_invalid_fertility_returns_422(client, calls):
    for bad in ({"v_pct": 120}, {"p_mg_dm3": -1}, {"ph": 5.5}, {"argila_pct": 50, "areia_pct": 20, "al_cmolc_dm3": 99}):
        r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "analise_solo": bad})
        assert r.status_code == 422, bad
    assert not calls


# Real engine
real = pytest.mark.skipif(not REAL_SERVICE, reason="serviço real indisponível")


def _rec(**kw):
    return svc.recommend(AREA, current_rotation=RA["rotacao_atual"], include_diagnosis=False, **kw)


def _rk(r):
    return {x["id"]: x for x in r["agora"]["ranking"] + r["proxima_safra"]["ranking"]}


@pytest.fixture(scope="module")
def base():
    return _rec()


@pytest.mark.integration
@real
def test_regression_without_fields_ranking_unchanged(base):
    assert {x["id_legado"]: x["nota"] for x in base["agora"]["ranking"] if "id_legado" in x} == EXPECTED
    assert "problemas_area" not in base["entrada"] and "ajustes_aplicados" not in base["metodologia"]
    for x in _rk(base).values():
        gap = " ".join(x["card"]["lacunas"])
        assert "Fertilidade e matéria orgânica não consideradas (não informadas)" in gap and "Problemas da área" in gap and "não informados" in gap
        assert "recuperacao_solo" not in x
        assert all("Fertilidade:" not in e for e in x["card"]["evidencias"])
        assert not any(i["cultura"] in ("Calagem",) for i in x["margem"]["itens"])
    # a soil analysis without fertility does not consider it either, and the applied adjustment says so
    r = _rec(soil_analysis={"argila_pct": 60, "areia_pct": 15})
    assert "Fertilidade não considerada (não informada)." in r["metodologia"]["ajustes_aplicados"]
    assert {k: v["criterios"] for k, v in _rk(r).items() if k.startswith("soja__")}["soja__trigo"]["pragas"] == _rk(base)["soja__trigo"]["criterios"]["pragas"]


@pytest.mark.integration
@real
def test_area_problems_move_the_ranking_in_the_expected_direction(base):
    b = _rk(base)
    r = _rec(area_problems=["mofo_branco"])
    x = _rk(r)
    assert x["soja__feijao_safrinha"]["criterios"]["pragas"] < b["soja__feijao_safrinha"]["criterios"]["pragas"]
    assert x["soja__feijao_safrinha"]["nota"] < b["soja__feijao_safrinha"]["nota"]
    assert x["soja__nabo_forrageiro"]["criterios"]["pragas"] < b["soja__nabo_forrageiro"]["criterios"]["pragas"]
    assert x["soja__milheto_crotalaria"]["criterios"]["pragas"] == pytest.approx(EA.soft_add(b["soja__milheto_crotalaria"]["criterios"]["pragas"], -X), abs=1e-3)  # summer soybean only
    pos = lambda rr, i: next(k for k, v in enumerate(sorted(_rk(rr).values(), key=lambda v: -v["nota"])) if v["id"] == i)  # noqa: E731
    assert pos(r, "soja__feijao_safrinha") >= pos(base, "soja__feijao_safrinha")
    assert r["entrada"]["problemas_area"] == ["mofo_branco"]
    assert "Fertilidade não considerada (não informada)." in r["metodologia"]["ajustes_aplicados"]
    assert any("fontes lidas" in a or "fonte lida" in a for a in r["metodologia"]["ajustes_aplicados"])
    assert any("mofo-branco" in e and "feijão" in e and "Brandão" in e for e in x["soja__feijao_safrinha"]["card"]["evidencias"])
    assert any("Problemas da área considerados: mofo-branco" in l for l in x["soja__feijao_safrinha"]["card"]["lacunas"])
    assert any("sem fonte confirmada" in l for l in x["soja__aveia_nabo"]["card"]["lacunas"])  # neutral cell is flagged

    n = _rk(_rec(area_problems=["nematoide"]))  # soybean -X in all; crotalaria +X on top; brachiaria and corn species-dependent -> neutral
    assert n["soja__milheto_crotalaria"]["criterios"]["pragas"] == pytest.approx(b["soja__milheto_crotalaria"]["criterios"]["pragas"])
    assert n["soja__milho_braquiaria"]["criterios"]["pragas"] == pytest.approx(EA.soft_add(b["soja__milho_braquiaria"]["criterios"]["pragas"], -X), abs=1e-3)
    assert n["soja__feijao_safrinha"]["criterios"]["pragas"] < b["soja__feijao_safrinha"]["criterios"]["pragas"]
    assert n["soja__milheto_crotalaria"]["criterios"]["pragas"] > n["soja__milho_safrinha"]["criterios"]["pragas"]

    mv = dict(current_rotation="milho_verao__milho_safrinha", summer_stage="maturacao", reference_date="2027-01-10", include_diagnosis=False)
    bm, cm = _rk(svc.recommend(AREA, **mv)), _rk(svc.recommend(AREA, area_problems=["cigarrinha"], **mv))
    assert cm["milho_verao__milho_safrinha"]["criterios"]["pragas"] == pytest.approx(EA.soft_add(bm["milho_verao__milho_safrinha"]["criterios"]["pragas"], -X), abs=1e-3)  # corn on corn only
    assert cm["milho_verao__trigo"]["criterios"]["pragas"] == bm["milho_verao__trigo"]["criterios"]["pragas"]
    c = _rk(_rec(area_problems=["cigarrinha"]))
    assert c["soja__milho_safrinha"]["criterios"] == b["soja__milho_safrinha"]["criterios"]  # single corn crop: neutral without source
    assert c["soja__trigo"]["criterios"] == b["soja__trigo"]["criterios"]

    k = _rk(_rec(area_problems=["compactacao"]))
    for i in ("soja__nabo_forrageiro", "soja__milho_braquiaria", "soja__milheto_crotalaria"):
        assert k[i]["criterios"]["solo"] > b[i]["criterios"]["solo"] and k[i]["criterios"]["pragas"] == b[i]["criterios"]["pragas"]
    assert k["soja__aveia_nabo"]["criterios"] == b["soja__aveia_nabo"]["criterios"]  # tested mix: no gain
    assert k["soja__trigo"]["criterios"]["solo"] == b["soja__trigo"]["criterios"]["solo"]


@pytest.mark.integration
@real
def test_poor_and_acid_fertility(base):
    b = _rk(base)
    r = _rec(soil_analysis={**POOR, "argila_pct": 55, "areia_pct": 15})
    x = _rk(r)
    for i in ("soja__trigo", "soja__milho_safrinha"):
        assert x[i]["criterios"]["solo"] < b[i]["criterios"]["solo"]
        assert x[i]["nota"] < b[i]["nota"]
        keys = [it["cultura"] for it in x[i]["margem"]["itens"]]
        assert "Calagem" in keys and any(c.startswith("Adubação P/K") for c in keys)
        assert x[i]["margem"]["total_r_ha"] < b[i]["margem"]["total_r_ha"]
    assert x["soja__nabo_forrageiro"]["criterios"]["solo"] > b["soja__nabo_forrageiro"]["criterios"]["solo"]  # sourced P/K recycler
    # brachiaria recycles P/K (+X) but its corn is acid-sensitive (-X at severity 2): net zero, both effects on the card
    assert x["soja__milho_braquiaria"]["criterios"]["solo"] == b["soja__milho_braquiaria"]["criterios"]["solo"]
    ev_b = " ".join(x["soja__milho_braquiaria"]["card"]["evidencias"])
    assert "Solo (P ou K baixos): favorece" in ev_b and "Solo (solo ácido): penaliza" in ev_b
    for i in ("soja__aveia_nabo", "soja__milheto_crotalaria"):  # no source for these mixes on P/K: neutral, and flagged
        assert x[i]["criterios"]["solo"] == b[i]["criterios"]["solo"]
        assert any("sem fonte confirmada" in l for l in x[i]["card"]["lacunas"])
    assert x["soja__soja_safrinha"]["criterios"]["solo"] < b["soja__soja_safrinha"]["criterios"]["solo"] if "soja__soja_safrinha" in x else True
    # recovery cost: on every candidate, liming in full (not diluted), income given up against the top-income option
    rec = {k: v["recuperacao_solo"] for k, v in x.items()}
    lime = {r["calagem_total_r_ha"] for r in rec.values()}
    assert len(lime) == 1 and lime.pop() > 0
    top = max(x.values(), key=lambda v: v["margem"]["incremental_r_ha"])
    assert rec[top["id"]]["renda_abdicada_r_ha"] == 0 and all(r["referencia_renda"] == top["rotacao"] for r in rec.values())
    assert rec["soja__milheto_crotalaria"]["renda_abdicada_r_ha"] > 0
    assert rec["soja__milho_braquiaria"]["credito_k2o_ate_r_ha"] == pytest.approx(round(40 * EA.K2O_PRICE_R_KG))
    assert rec["soja__trigo"]["credito_k2o_ate_r_ha"] is None
    assert any(e.startswith("Recuperar o solo com esta opção") for e in x["soja__trigo"]["card"]["evidencias"])
    # oat (no P/K model, no solo effect) pays only the area-level liming, the same amount as wheat; solo/pragas criteria do not move
    ca, cb = x["soja__aveia"]["criterios"], b["soja__aveia"]["criterios"]
    assert {k: v for k, v in ca.items() if k != "renda"} == {k: v for k, v in cb.items() if k != "renda"} and ca["renda"] < cb["renda"]
    liming = {i: next(it["margem_r_ha"] for it in x[i]["margem"]["itens"] if it["cultura"] == "Calagem") for i in ("soja__aveia", "soja__trigo")}
    assert liming["soja__aveia"] == pytest.approx(liming["soja__trigo"], abs=1.0)
    assert (b["soja__aveia"]["margem"]["total_r_ha"] - x["soja__aveia"]["margem"]["total_r_ha"]) == pytest.approx(-liming["soja__aveia"], abs=1.0)
    # every candidate now carries the liming, so absolute scores drop; the recycling bonus must still lift radish relative to oat
    assert (x["soja__nabo_forrageiro"]["nota"] - x["soja__aveia"]["nota"]) > (b["soja__nabo_forrageiro"]["nota"] - b["soja__aveia"]["nota"])
    assert x["soja__trigo"]["nota"] < b["soja__trigo"]["nota"]
    assert "Problemas da área não informados: não considerados." in r["metodologia"]["ajustes_aplicados"]
    assert any("Fertilidade informada" in a for a in r["metodologia"]["ajustes_aplicados"])
    assert all("Fertilidade não considerada" not in " ".join(v["card"]["lacunas"]) for v in x.values())
    ev = " ".join(x["soja__trigo"]["card"]["evidencias"])
    assert "Calagem" in ev and "Manual de Adubação e Calagem" in ev and "CBPTT 2020" in ev and "argila" in ev.lower()
    assert r["entrada"]["analise_solo"]["v_pct"] == 30 and "problemas_area" not in r["entrada"]


@pytest.mark.integration
@real
def test_partial_fertility_and_diagnosis(base):
    r = _rec(soil_analysis={"p_mg_dm3": 2})  # only P: no liming (V% and CEC missing), no acidity penalty
    x = _rk(r)["soja__trigo"]
    assert [i["cultura"] for i in x["margem"]["itens"]].count("Calagem") == 0
    gap = " ".join(x["card"]["lacunas"])
    assert "Calagem não calculada" in gap and "Fertilidade parcial" in gap and "Argila não informada" in gap  # no clay: most demanding band
    assert x["criterios"]["solo"] == _rk(base)["soja__trigo"]["criterios"]["solo"]
    d = svc.diagnose(AREA, soil_analysis=POOR)
    assert d["fertilidade"]["classes"]["al"] == "medio" and d["fertilidade"]["argila_faixa_g_kg"] == "<250" and d["solo"]["fonte"] != "análise de solo do produtor"
    assert "Manual de Adubação e Calagem" in d["fertilidade"]["fonte"]
    d2 = svc.diagnose(AREA, soil_analysis={**POOR, "argila_pct": 55, "areia_pct": 15})
    assert d2["fertilidade"]["argila_faixa_g_kg"] == ">400" and d2["fertilidade"]["argila_origem"] == "informada"
    assert "fertilidade" not in svc.diagnose(AREA)


@pytest.mark.integration
@real
def test_invalid_values_in_real_engine():
    with pytest.raises(svc.InvalidInput):
        _rec(area_problems=["ferrugem"])
    with pytest.raises(svc.InvalidInput):
        _rec(soil_analysis={"v_pct": 150})


# Organic matter, soft bound and recovery cost
@pytest.mark.parametrize("corg,expected", [(3.9, "muito_baixo"), (4, "baixo"), (8.6, "baixo"), (9, "medio"), (14.9, "medio"),
                                           (15, "alto"), (20, "alto"), (20.5, "muito_alto")])
def test_organic_carbon_classes_manual_pr(corg, expected):
    f = EA.prepare_fertility(None, None, corg)
    assert f["classes"] == {"mo": expected} and f["mo_baixa"] == (expected in EA.LOW)


def test_low_organic_matter_effects_have_sources_and_direction():
    state = {"problemas": [], "fert": EA.prepare_fertility(None, None, 7.0)}  # MO ~1.2 %
    d = {s: EA.adjustment(_cand_crops(f"Soja → {n}"), state)["solo"] for s, n in (("braq", "milho safrinha + braquiária"),
                                                                           ("mil", "milheto/crotalária (cobertura)"), ("pou", "pousio"),
                                                                           ("mil_s", "milho safrinha"), ("trigo", "trigo"))}
    assert d["braq"] == d["mil"] == X and d["pou"] == -X and d["mil_s"] == d["trigo"] == 0
    ev = " ".join(EA.card(_cand_crops("Soja → pousio"), state)["evidencias"])
    assert "Resende et al. 2021" in ev and "Quadro 4" in ev and "matéria orgânica baixa" in ev
    assert EA.adjustment(_cand_crops("Soja → pousio"), {"problemas": [], "fert": EA.prepare_fertility(None, None, 25.0)})["solo"] == 0


def test_acidity_is_graded_and_sourced():
    sev1 = EA.prepare_fertility({"al_cmolc_dm3": 1.0})  # Al medio -> severity 1
    sev2 = EA.prepare_fertility({"al_cmolc_dm3": 2.0})
    c = _cand_crops("Soja → trigo")
    assert EA.adjustment(c, {"fert": sev1})["solo"] == pytest.approx(-X / 2) and EA.adjustment(c, {"fert": sev2})["solo"] == pytest.approx(-X)
    assert EA.adjustment(_cand_crops("Soja → aveia (cobertura/palha)"), {"fert": sev2})["solo"] == 0


@pytest.mark.parametrize("base", [0.0, 0.3, 0.7, 0.95, 1.0])
def test_soft_add_never_saturates_and_is_identity_at_zero(base):
    assert EA.soft_add(base, 0.0) == base
    up, up2 = EA.soft_add(base, 0.15), EA.soft_add(base, 0.30)
    dn, dn2 = EA.soft_add(base, -0.15), EA.soft_add(base, -0.30)
    assert 0.0 <= dn2 <= dn <= base <= up <= up2 <= 1.0
    if 0 < base < 1:
        assert up < up2 < 1.0 and 0.0 < dn2 < dn  # two different adjustments never tie at the bound
        assert abs(EA.soft_add(base, 1e-6) - base - 1e-6) < 1e-9  # slope 1 at zero


def test_recovery_cost_only_when_soil_needs_it():
    c = _cand_crops("Soja → milheto/crotalária (cobertura)")
    marg, best = {"incremental": -300.0}, ("Soja → milho safrinha", 1500.0)
    assert EA.recovery(c, None, marg, best) is None
    assert EA.recovery(c, {"fert": EA.prepare_fertility({"p_mg_dm3": 80}, 50)}, marg, best) is None  # rich soil
    r = EA.recovery(c, {"problemas": [], "fert": EA.prepare_fertility(POOR, 55, 7.0)}, marg, best)
    nc = (EA.V2_AREA - 30) / 100 * 9 / EA.PRNT
    assert r["calagem_total_r_ha"] == pytest.approx(nc * EA.LIME_R_T) and r["renda_abdicada_r_ha"] == 1800.0
    assert r["total_primeiro_ano_r_ha"] == pytest.approx(nc * EA.LIME_R_T + 1800.0) and r["credito_k2o_ate_r_ha"] is None
    assert "R$ 1.800/ha" in r["texto"] and "anos de palhada" in r["texto"]
