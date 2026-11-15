"""Service-layer tests (run: uv run python tests/test_service.py  or  uv run pytest tests/test_service.py)."""
import json
import time

from field_shift.core import InvalidInput, OutOfRegion, diagnose, options
from field_shift.core import recommend as _recommend


def recommend(area, **kw):
    """`current_rotation` is required in the service; the old tests use soybean → second-season corn (catalog calendar assumption)."""
    kw.setdefault("current_rotation", "soja__milho_safrinha")
    return _recommend(area, **kw)

# Scores of the 6 old rotations (summer soybean), by old slug (`id_legado`): they do not change with the larger catalog (absolute scale).
EXPECTED = {"milho_braquiaria": 0.821, "milho_safrinha": 0.774, "milheto_crotalaria": 0.757, "aveia": 0.7, "pousio": 0.55, "trigo": 0.466}


def _old(r):
    return {x["id_legado"]: x["nota"] for x in r["agora"]["ranking"] if "id_legado" in x}


def _t(f, *a, **k):
    t0 = time.perf_counter()
    r = f(*a, **k)
    json.dumps(r, allow_nan=False)
    return r, time.perf_counter() - t0


def test_field_72638():
    r, dt = _t(recommend, {"talhao_id": "72638"})
    assert _old(r) == EXPECTED
    assert r["entrada"]["rotacao_atual"] == "soja__milho_safrinha" and r["atual"]["atual"] and r["atual"]["id_legado"] == "milho_safrinha"
    assert [a["id"] for a in r["alternativas"]] == ["soja__milho_braquiaria", "soja__milheto_crotalaria", "soja__aveia_nabo"]
    assert [e["id"] for e in r["eliminadas"]][0] == "soja__soja_safrinha" and len(r["eliminadas"]) == 7
    # incremental margin and S scale (Cascavel soybean); rounded output (R$ without decimals, criteria with 3)
    m = _rk(r)
    assert m["milho_safrinha"]["margem"]["incremental_r_ha"] == 1762 and m["milho_braquiaria"]["margem"]["incremental_r_ha"] == 1802
    assert m["trigo"]["margem"]["escala_S_r_ha"] == 1192
    assert r["ranking"][0]["criterios"]["renda"] == 1.0 and m["trigo"]["criterios"]["renda"] == 0.0  # both clipped
    # "why" compared with the current one
    top = r["ranking"][0]["card"]["por_que"]
    assert top.startswith("Em relação à atual (milho safrinha):") and "melhora a saúde do solo" in top  # income is clipped at 1 for both corn options
    current = r["atual"]["card"]["por_que"]
    assert current.startswith("É a rotação atual; ficou em 2º lugar entre 10 opções válidas. A melhor alternativa (milho safrinha + braquiária)")
    print("72638", round(dt, 2), "s", [(x["id"], round(x["nota"], 2)) for x in r["ranking"]])


def test_polygon_cascavel():
    # ~100 ha of cropland ~15 km east of Cascavel (checked in MapBiomas through the diagnosis)
    lon, lat, h = -53.30, -24.90, 0.0045
    g = {"type": "Polygon", "coordinates": [[[lon - h, lat - h], [lon + h, lat - h], [lon + h, lat + h], [lon - h, lat + h], [lon - h, lat - h]]]}
    r, dt = _t(recommend, {"geometry": {"type": "Feature", "properties": {}, "geometry": g}}, pesos={"renda": 10}, adjustments={"precos": {"soja": 100}, "custos": {"milho": 4000}, "linha_custo": "cot"})
    d = r["diagnostico"]
    print("poligono", round(dt, 2), "s", d["area"]["area_ha"], d["area"]["municipio"], [(h["ano"], h["nome_classe"]) for h in d["historico"][-3:]], d["avisos"])
    assert d["area"]["origem"] == "geometry" and r["entrada"]["rotacao_atual"] == "soja__milho_safrinha"
    assert any("assumida" in a for a in r["avisos"])
    return r


def test_point_guaira():
    r, dt = _t(recommend, {"lat": -24.20, "lon": -54.20}, n_alternatives=2, include_diagnosis=False)
    assert len(r["alternativas"]) == 2 and "diagnostico" not in r
    d, dt2 = _t(diagnose, {"lat": -24.20, "lon": -54.20})
    print("Guaíra point", round(dt, 2), d["area"]["area_ha"], d["area"]["municipio"], [(h["ano"], h["nome_classe"]) for h in d["historico"][-3:]], d["avisos"])


def test_errors():
    for a, exc in [({"lat": -23.55, "lon": -46.63}, OutOfRegion), ({"talhao_id": "x"}, InvalidInput), ({}, InvalidInput),
                   ({"geometry": {"type": "Polygon", "coordinates": [[[-53, -24], [-52, -25], [-53, -25], [-52, -24], [-53, -24]]]}}, InvalidInput),
                   ({"geometry": {"type": "Polygon", "coordinates": [[[-54, -24], [-53, -24], [-53, -25], [-54, -25], [-54, -24]]]}}, InvalidInput)]:
        try:
            recommend(a)
        except exc as e:
            print("ok", exc.__name__, str(e)[:90])
        else:
            raise AssertionError(a)
    for kw in [dict(sowing_second="02/02"), dict(current_rotation="x"), dict(pesos={"x": 1}), dict(pesos={"renda": 11}), dict(adjustments={"custos": {"x": 1}})]:
        try:
            recommend({"talhao_id": "72638"}, **kw)
        except InvalidInput as e:
            print("ok InvalidInput", str(e)[:70])
        else:
            raise AssertionError(kw)


def test_options_and_current_eliminated():
    o, _ = _t(options)
    assert o["regiao"]["n_municipios"] == 399 and o["talhoes_demo"][0]["id"] == "72638"
    r, _ = _t(recommend, {"talhao_id": "72638"}, current_rotation="soja_safrinha", include_diagnosis=False)  # slug antigo
    assert r["atual"]["eliminada"] and r["atual"]["id"] == "soja__soja_safrinha" and not any(x["atual"] for x in r["ranking"])


# --------------------------------------------------------------------------- optional inputs (own data)
T = {"talhao_id": "72638"}
TYPICAL_SOIL = {"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5, "cad_mm_cm": 1.4}


def _rk(r):
    """Ranking by old slug (`id_legado`) when there is one, otherwise by the new id."""
    return {x.get("id_legado", x["id"]): x for x in r["agora"]["ranking"] + r["proxima_safra"]["ranking"]}


def test_regression_without_new_inputs():
    """Without the new inputs, the ranking is identical to the previous one and the input/methodology get no new keys."""
    r, _ = _t(recommend, T)
    assert _old(r) == EXPECTED
    assert set(r["entrada"]) == {"semeadura_safrinha", "pesos", "rotacao_atual", "estagio_verao", "colheita_prevista", "data_referencia",
                                 "ajustes", "n_alternativas"}
    assert "ajustes_aplicados" not in r["metodologia"]
    assert all("irrigacao" not in x for x in r["ranking"])
    assert not any("terceirizar" in a for x in r["ranking"] for a in x["card"]["avisos"])


def test_own_yield():
    r, _ = _t(recommend, T, adjustments={"produtividade": {"soja": 70, "milho": 120, "trigo": 50}})
    base, _ = _t(recommend, T)
    m, mb = _rk(r)["milho_safrinha"]["margem"], _rk(base)["milho_safrinha"]["margem"]
    soy, corn = m["itens"][0], m["itens"][1]
    assert soy["rendimento_sc_ha"] == 70 and corn["rendimento_sc_ha"] == 120
    assert "informado pelo produtor" in soy["fonte"] and "informado pelo produtor" in corn["fonte"]
    assert any("informado pelo produtor" in e for e in _rk(r)["milho_safrinha"]["card"]["evidencias"])
    # a given soybean yield changes the S scale; the bad year scales proportionally (p20/PAM mean)
    assert m["escala_S_r_ha"] > mb["escala_S_r_ha"] and m["total_r_ha"] > mb["total_r_ha"]
    assert any("p20/média da PAM" in e for e in _rk(r)["milho_safrinha"]["card"]["evidencias"])
    assert any("Produtividade informada" in a for a in r["metodologia"]["ajustes_aplicados"])
    # alias milho_2safra equivale a milho
    r2, _ = _t(recommend, T, adjustments={"produtividade": {"soja": 70, "milho_2safra": 120, "trigo": 50}})
    assert {x["id"]: x["nota"] for x in r2["ranking"]} == {x["id"]: x["nota"] for x in r["ranking"]}


def test_soil_analysis():
    base, _ = _t(recommend, T, include_diagnosis=False)
    r, _ = _t(recommend, T, soil_analysis=TYPICAL_SOIL)
    s = r["diagnostico"]["solo"]
    assert s["fonte"] == "análise de solo do produtor" and s["cad_mm_cm"]["0-30"] == 1.4 and s["p30"]["clay"] == 65
    assert r["entrada"]["analise_solo"]["cad_mm_cm"] == 1.4
    assert _rk(r)["milho_safrinha"]["criterios"]["agua"] > _rk(base)["milho_safrinha"]["criterios"]["agua"]
    assert any("análise de solo do produtor" in e for e in _rk(r)["milho_safrinha"]["card"]["evidencias"])
    # without cad_mm_cm: Saxton & Rawls with the given values; OM as organic carbon is equivalent
    r_sr, _ = _t(recommend, T, soil_analysis={"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5}, include_diagnosis=False)
    r_c, _ = _t(recommend, T, soil_analysis={"argila_pct": 65, "areia_pct": 10, "carbono_organico_g_kg": 3.5 / 1.724 * 10}, include_diagnosis=False)
    assert _rk(r_sr)["milho_safrinha"]["criterios"]["agua"] == _rk(r_c)["milho_safrinha"]["criterios"]["agua"]
    # AWC only is also valid; diagnose accepts the analysis
    d, _ = _t(diagnose, T, soil_analysis={"cad_mm_cm": 1.0})
    assert d["solo"]["fonte"] == "análise de solo do produtor" and d["solo"]["classe_textura"] is None


def test_invalid_soil_analysis():
    ruins = [{"argila_pct": 60, "areia_pct": 50}, {"argila_pct": 101, "areia_pct": 0}, {"argila_pct": 50},
             {"argila_pct": 50, "areia_pct": 10, "ph": 9.5}, {"argila_pct": 50, "areia_pct": 10, "ph": 2},
             {"cad_mm_cm": 0.1}, {"cad_mm_cm": 3.5}, {"ph": 5}, {"argila_pct": 50, "areia_pct": 10, "x": 1},
             {"argila_pct": 50, "areia_pct": 10, "materia_organica_pct": 3, "carbono_organico_g_kg": 20},
             {"argila_pct": 50, "areia_pct": 10, "materia_organica_pct": -1}, "x"]
    for a in ruins:
        try:
            recommend(T, soil_analysis=a, include_diagnosis=False)
        except InvalidInput:
            pass
        else:
            raise AssertionError(a)


def test_constraints_excluded_and_no_buyer():
    r, _ = _t(recommend, T, constraints={"culturas_excluidas": ["trigo"], "sem_comprador": ["milho", "aveia_grao"]}, include_diagnosis=False)
    el = {e["id"]: e["motivos"] for e in r["eliminadas"]}
    assert el["soja__trigo"] == ["Excluída pelo produtor."]  # slug antigo = soja__trigo; milho_verao__trigo segue valendo
    assert el["milho_verao__trigo"] == ["Sem comprador local informado pelo produtor (milho)."]  # the old exclusion only applies to summer soybean
    assert "Sem comprador local informado pelo produtor" in el["soja__milho_safrinha"][0] and "soja__milho_braquiaria" in el
    assert "Sem comprador local informado pelo produtor (milho)" in el["milho_verao__aveia"][0]  # summer corn also needs a buyer
    assert [x["id"] for x in r["ranking"]][:3] == ["soja__milheto_crotalaria", "soja__aveia_nabo", "soja__aveia"]
    assert r["atual"]["eliminada"] and r["entrada"]["restricoes"]["sem_comprador"] == ["milho", "aveia_grao"]
    assert r["entrada"]["restricoes"]["culturas_excluidas"] == ["soja__trigo"]
    r2, _ = _t(recommend, T, constraints={"sem_comprador": ["trigo"]}, include_diagnosis=False)
    assert {e["id"] for e in r2["eliminadas"]} >= {"soja__soja_safrinha", "soja__trigo", "milho_verao__trigo"}
    # tudo eliminado -> EntradaInvalida
    try:
        recommend(T, constraints={"culturas_excluidas": [i for i in options()["rotacoes"] for i in [i["id"]]]})
    except InvalidInput:
        pass
    else:
        raise AssertionError("todas eliminadas")


def test_constraints_machines():
    base, _ = _t(recommend, T, include_diagnosis=False)
    r, _ = _t(recommend, T, constraints={"maquinas": {"plataforma_milho": False, "semeadora_consorcio": False}}, include_diagnosis=False)
    rb, rr = _rk(base), _rk(r)
    assert "milho_safrinha" in rr and "milho_braquiaria" in rr  # does not eliminate
    assert "milho_verao__aveia" in rr
    assert any("plataforma de milho" in a for a in rr["milho_safrinha"]["card"]["avisos"])
    assert any("semeadora de consórcio" in a for a in rr["milho_braquiaria"]["card"]["avisos"])
    assert rr["milho_safrinha"]["margem"]["total_r_ha"] == rb["milho_safrinha"]["margem"]["total_r_ha"] - 250
    assert rr["milho_verao__aveia"]["margem"]["total_r_ha"] == rb["milho_verao__aveia"]["margem"]["total_r_ha"] - 250  # summer-corn harvest
    assert rr["milho_braquiaria"]["margem"]["total_r_ha"] == rb["milho_braquiaria"]["margem"]["total_r_ha"] - 330
    assert rr["trigo"]["margem"] == rb["trigo"]["margem"] and not any("terceirizar" in a for a in rr["trigo"]["card"]["avisos"])
    # machine true / omitted = owned
    r_ok, _ = _t(recommend, T, constraints={"maquinas": {"plataforma_milho": True}}, include_diagnosis=False)
    assert _old(r_ok) == EXPECTED


def test_mercado_no_card():
    r, _ = _t(recommend, T, include_diagnosis=False)
    m = {k: v["card"]["mercado"] for k, v in _rk(r).items()}
    assert m["milho_safrinha"]["nivel"] == "alto" and m["trigo"]["nivel"] == "médio" and m["aveia"]["nivel"] == "não se aplica"
    assert any(e.startswith("Mercado no Oeste do PR: alto") for e in _rk(r)["milho_safrinha"]["card"]["evidencias"])


def test_irrigation():
    base, _ = _t(recommend, T, include_diagnosis=False)
    r, _ = _t(recommend, T, irrigation={"disponivel": True}, include_diagnosis=False)
    rb, rr = _rk(base), _rk(r)
    for k in ("milho_safrinha", "milho_braquiaria", "trigo", "soja__sorgo", "soja__feijao_safrinha"):
        assert rr[k]["criterios"]["agua"] >= rb[k]["criterios"]["agua"] and rr[k]["irrigacao"]["lamina_media_mm_ano"] > 0
        assert rr[k]["margem"]["total_r_ha"] < rb[k]["margem"]["total_r_ha"]
        assert any(e.startswith("Irrigado: lâmina média") for e in rr[k]["card"]["evidencias"])
    assert rr["milho_safrinha"]["criterios"]["risco"] > rb["milho_safrinha"]["criterios"]["risco"]  # no dry spell
    assert rr["trigo"]["criterios"]["risco"] == rb["trigo"]["criterios"]["risco"]  # wheat only has frost
    for k in ("aveia", "milheto_crotalaria", "pousio", "nabo_forrageiro"):  # cover/fallow: not irrigated
        k = k if k in rr else f"soja__{k}"
        assert "irrigacao" not in rr[k] and rr[k]["criterios"] == rb[k]["criterios"]
    # disponivel=False = sequeiro; custo maior aumenta o desconto
    r0, _ = _t(recommend, T, irrigation={"disponivel": False}, include_diagnosis=False)
    assert _old(r0) == EXPECTED
    r2, _ = _t(recommend, T, irrigation={"disponivel": True, "custo_r_mm_ha": 8, "lamina_max_mm_dia": 3}, include_diagnosis=False)
    ir2 = _rk(r2)["milho_safrinha"]["irrigacao"]
    assert abs(ir2["custo_r_ha"] - 8 * ir2["lamina_media_mm_ano"]) < 1 and r2["entrada"]["irrigacao"]["lamina_max_mm_dia"] == 3


def test_invalid_new_inputs():
    for kw in [dict(constraints={"culturas_excluidas": ["arroz"]}), dict(constraints={"sem_comprador": ["soja"]}),
               dict(constraints={"maquinas": {"trator": True}}), dict(constraints={"maquinas": {"plataforma_milho": "sim"}}),
               dict(constraints={"x": 1}), dict(irrigation={}), dict(irrigation={"disponivel": "sim"}),
               dict(irrigation={"disponivel": True, "lamina_max_mm_dia": 0}), dict(irrigation={"disponivel": True, "custo_r_mm_ha": -1}),
               dict(adjustments={"produtividade": {"soja": 0}}), dict(adjustments={"produtividade": {"arroz": 5}}),
               dict(adjustments={"produtividade": {"milho": 100, "milho_2safra": 90}}), dict(adjustments={"produtividade": {"soja": "x"}})]:
        try:
            recommend(T, include_diagnosis=False, **kw)
        except InvalidInput:
            pass
        else:
            raise AssertionError(kw)


if __name__ == "__main__":
    t0 = time.perf_counter()
    test_field_72638()
    print("frio total", round(time.perf_counter() - t0, 2))
    test_polygon_cascavel(); test_point_guaira(); test_errors(); test_options_and_current_eliminated()
    from field_shift.core import warm_up
    t0 = time.perf_counter(); warm_up(); print("aquecer (ja quente)", round(time.perf_counter() - t0, 2))
    t0 = time.perf_counter(); recommend({"lat": -24.5, "lon": -53.9}); print("quente, ponto novo", round(time.perf_counter() - t0, 2))
    print("TUDO OK")


def test_technical_tie():
    # 15/03: millet/crotalaria and corn + brachiaria are less than 0.02 apart on field 72638
    r = recommend({"talhao_id": "72638"}, sowing_second="15/03", include_diagnosis=False)
    e = r["agora"]["empate_tecnico"]
    assert e is not None and e["ids"][:2] == ["soja__milheto_crotalaria", "soja__milho_braquiaria"] and 0 <= e["diferenca"] < 0.02
    tied = [x for x in r["agora"]["ranking"] if x["id"] in e["ids"]]
    assert all(x["card"]["avisos"][0].startswith("Empate técnico") for x in tied)
    assert not any(a.startswith("Empate técnico") for x in r["agora"]["ranking"] if x["id"] not in e["ids"] for a in x["card"]["avisos"])
    # 15/01: corn + brachiaria clearly ahead
    assert recommend({"talhao_id": "72638"}, sowing_second="15/01", include_diagnosis=False)["agora"]["empate_tecnico"] is None
