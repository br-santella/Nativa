"""Testes da camada de serviço (rodar: uv run python tests/test_servico.py  ou  uv run pytest tests/test_servico.py)."""
import json
import time

from field_shift.motor import EntradaInvalida, ForaDaRegiao, diagnosticar, opcoes
from field_shift.motor import recomendar as _recomendar


def recomendar(area, **kw):
    """`rotacao_atual` é obrigatória no serviço; os testes antigos usam soja → milho safrinha (premissa de calendário do catálogo)."""
    kw.setdefault("rotacao_atual", "soja__milho_safrinha")
    return _recomendar(area, **kw)

# Notas das 6 rotações antigas (soja no verão), pelo slug antigo (`id_legado`): não mudam com o catálogo maior (escala absoluta).
ESPERADO = {"milho_braquiaria": 0.821, "milho_safrinha": 0.774, "milheto_crotalaria": 0.757, "aveia": 0.7, "pousio": 0.55, "trigo": 0.466}


def _antigas(r):
    return {x["id_legado"]: x["nota"] for x in r["agora"]["ranking"] if "id_legado" in x}


def _t(f, *a, **k):
    t0 = time.perf_counter()
    r = f(*a, **k)
    json.dumps(r, allow_nan=False)
    return r, time.perf_counter() - t0


def test_talhao_72638():
    r, dt = _t(recomendar, {"talhao_id": "72638"})
    assert _antigas(r) == ESPERADO
    assert r["entrada"]["rotacao_atual"] == "soja__milho_safrinha" and r["atual"]["atual"] and r["atual"]["id_legado"] == "milho_safrinha"
    assert [a["id"] for a in r["alternativas"]] == ["soja__milho_braquiaria", "soja__milheto_crotalaria", "soja__aveia_nabo"]
    assert [e["id"] for e in r["eliminadas"]][0] == "soja__soja_safrinha" and len(r["eliminadas"]) == 7
    # margem incremental e escala S (soja de Cascavel); saída arredondada (R$ sem casas, critérios com 3)
    m = _rk(r)
    assert m["milho_safrinha"]["margem"]["incremental_r_ha"] == 1762 and m["milho_braquiaria"]["margem"]["incremental_r_ha"] == 1802
    assert m["trigo"]["margem"]["escala_S_r_ha"] == 1192
    assert r["ranking"][0]["criterios"]["renda"] == 1.0 and m["trigo"]["criterios"]["renda"] == 0.0  # both clipped
    # "por quê" comparado com a atual
    top = r["ranking"][0]["card"]["por_que"]
    assert top.startswith("Em relação à atual (milho safrinha):") and "melhora a saúde do solo" in top  # income is clipped at 1 for both corn options
    atual = r["atual"]["card"]["por_que"]
    assert atual.startswith("É a rotação atual; ficou em 2º lugar entre 10 opções válidas. A melhor alternativa (milho safrinha + braquiária)")
    print("72638", round(dt, 2), "s", [(x["id"], round(x["nota"], 2)) for x in r["ranking"]])


def test_poligono_cascavel():
    # ~100 ha em lavoura a ~15 km a leste de Cascavel (conferido no MapBiomas pelo diagnóstico)
    lon, lat, h = -53.30, -24.90, 0.0045
    g = {"type": "Polygon", "coordinates": [[[lon - h, lat - h], [lon + h, lat - h], [lon + h, lat + h], [lon - h, lat + h], [lon - h, lat - h]]]}
    r, dt = _t(recomendar, {"geometry": {"type": "Feature", "properties": {}, "geometry": g}}, pesos={"renda": 10}, ajustes={"precos": {"soja": 100}, "custos": {"milho": 4000}, "linha_custo": "cot"})
    d = r["diagnostico"]
    print("poligono", round(dt, 2), "s", d["area"]["area_ha"], d["area"]["municipio"], [(h["ano"], h["nome_classe"]) for h in d["historico"][-3:]], d["avisos"])
    assert d["area"]["origem"] == "geometry" and r["entrada"]["rotacao_atual"] == "soja__milho_safrinha"
    assert any("assumida" in a for a in r["avisos"])
    return r


def test_ponto_guaira():
    r, dt = _t(recomendar, {"lat": -24.20, "lon": -54.20}, n_alternativas=2, incluir_diagnostico=False)
    assert len(r["alternativas"]) == 2 and "diagnostico" not in r
    d, dt2 = _t(diagnosticar, {"lat": -24.20, "lon": -54.20})
    print("ponto Guaíra", round(dt, 2), d["area"]["area_ha"], d["area"]["municipio"], [(h["ano"], h["nome_classe"]) for h in d["historico"][-3:]], d["avisos"])


def test_erros():
    for a, exc in [({"lat": -23.55, "lon": -46.63}, ForaDaRegiao), ({"talhao_id": "x"}, EntradaInvalida), ({}, EntradaInvalida),
                   ({"geometry": {"type": "Polygon", "coordinates": [[[-53, -24], [-52, -25], [-53, -25], [-52, -24], [-53, -24]]]}}, EntradaInvalida),
                   ({"geometry": {"type": "Polygon", "coordinates": [[[-54, -24], [-53, -24], [-53, -25], [-54, -25], [-54, -24]]]}}, EntradaInvalida)]:
        try:
            recomendar(a)
        except exc as e:
            print("ok", exc.__name__, str(e)[:90])
        else:
            raise AssertionError(a)
    for kw in [dict(semeadura_safrinha="02/02"), dict(rotacao_atual="x"), dict(pesos={"x": 1}), dict(pesos={"renda": 11}), dict(ajustes={"custos": {"x": 1}})]:
        try:
            recomendar({"talhao_id": "72638"}, **kw)
        except EntradaInvalida as e:
            print("ok EntradaInvalida", str(e)[:70])
        else:
            raise AssertionError(kw)


def test_opcoes_e_atual_eliminada():
    o, _ = _t(opcoes)
    assert o["regiao"]["n_municipios"] == 399 and o["talhoes_demo"][0]["id"] == "72638"
    r, _ = _t(recomendar, {"talhao_id": "72638"}, rotacao_atual="soja_safrinha", incluir_diagnostico=False)  # slug antigo
    assert r["atual"]["eliminada"] and r["atual"]["id"] == "soja__soja_safrinha" and not any(x["atual"] for x in r["ranking"])


# --------------------------------------------------------------------------- entradas opcionais (dados próprios)
T = {"talhao_id": "72638"}
SOLO_TIPICO = {"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5, "cad_mm_cm": 1.4}


def _rk(r):
    """Ranking por slug antigo (`id_legado`) quando existe, senão pelo id novo."""
    return {x.get("id_legado", x["id"]): x for x in r["agora"]["ranking"] + r["proxima_safra"]["ranking"]}


def test_regressao_sem_entradas_novas():
    """Sem as entradas novas, o ranking é idêntico ao anterior e a entrada/metodologia não ganham chaves novas."""
    r, _ = _t(recomendar, T)
    assert _antigas(r) == ESPERADO
    assert set(r["entrada"]) == {"semeadura_safrinha", "pesos", "rotacao_atual", "estagio_verao", "colheita_prevista", "data_referencia",
                                 "ajustes", "n_alternativas"}
    assert "ajustes_aplicados" not in r["metodologia"]
    assert all("irrigacao" not in x for x in r["ranking"])
    assert not any("terceirizar" in a for x in r["ranking"] for a in x["card"]["avisos"])


def test_produtividade_propria():
    r, _ = _t(recomendar, T, ajustes={"produtividade": {"soja": 70, "milho": 120, "trigo": 50}})
    base, _ = _t(recomendar, T)
    m, mb = _rk(r)["milho_safrinha"]["margem"], _rk(base)["milho_safrinha"]["margem"]
    soja, milho = m["itens"][0], m["itens"][1]
    assert soja["rendimento_sc_ha"] == 70 and milho["rendimento_sc_ha"] == 120
    assert "informado pelo produtor" in soja["fonte"] and "informado pelo produtor" in milho["fonte"]
    assert any("informado pelo produtor" in e for e in _rk(r)["milho_safrinha"]["card"]["evidencias"])
    # soja informada muda a escala S; ano ruim escala proporcional (p20/média da PAM)
    assert m["escala_S_r_ha"] > mb["escala_S_r_ha"] and m["total_r_ha"] > mb["total_r_ha"]
    assert any("p20/média da PAM" in e for e in _rk(r)["milho_safrinha"]["card"]["evidencias"])
    assert any("Produtividade informada" in a for a in r["metodologia"]["ajustes_aplicados"])
    # alias milho_2safra equivale a milho
    r2, _ = _t(recomendar, T, ajustes={"produtividade": {"soja": 70, "milho_2safra": 120, "trigo": 50}})
    assert {x["id"]: x["nota"] for x in r2["ranking"]} == {x["id"]: x["nota"] for x in r["ranking"]}


def test_analise_solo():
    base, _ = _t(recomendar, T, incluir_diagnostico=False)
    r, _ = _t(recomendar, T, analise_solo=SOLO_TIPICO)
    s = r["diagnostico"]["solo"]
    assert s["fonte"] == "análise de solo do produtor" and s["cad_mm_cm"]["0-30"] == 1.4 and s["p30"]["clay"] == 65
    assert r["entrada"]["analise_solo"]["cad_mm_cm"] == 1.4
    assert _rk(r)["milho_safrinha"]["criterios"]["agua"] > _rk(base)["milho_safrinha"]["criterios"]["agua"]
    assert any("análise de solo do produtor" in e for e in _rk(r)["milho_safrinha"]["card"]["evidencias"])
    # sem cad_mm_cm: Saxton & Rawls com os valores informados; MO como carbono orgânico equivale
    r_sr, _ = _t(recomendar, T, analise_solo={"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5}, incluir_diagnostico=False)
    r_c, _ = _t(recomendar, T, analise_solo={"argila_pct": 65, "areia_pct": 10, "carbono_organico_g_kg": 3.5 / 1.724 * 10}, incluir_diagnostico=False)
    assert _rk(r_sr)["milho_safrinha"]["criterios"]["agua"] == _rk(r_c)["milho_safrinha"]["criterios"]["agua"]
    # só CAD também vale; diagnosticar aceita a análise
    d, _ = _t(diagnosticar, T, analise_solo={"cad_mm_cm": 1.0})
    assert d["solo"]["fonte"] == "análise de solo do produtor" and d["solo"]["classe_textura"] is None


def test_analise_solo_invalida():
    ruins = [{"argila_pct": 60, "areia_pct": 50}, {"argila_pct": 101, "areia_pct": 0}, {"argila_pct": 50},
             {"argila_pct": 50, "areia_pct": 10, "ph": 9.5}, {"argila_pct": 50, "areia_pct": 10, "ph": 2},
             {"cad_mm_cm": 0.1}, {"cad_mm_cm": 3.5}, {"ph": 5}, {"argila_pct": 50, "areia_pct": 10, "x": 1},
             {"argila_pct": 50, "areia_pct": 10, "materia_organica_pct": 3, "carbono_organico_g_kg": 20},
             {"argila_pct": 50, "areia_pct": 10, "materia_organica_pct": -1}, "x"]
    for a in ruins:
        try:
            recomendar(T, analise_solo=a, incluir_diagnostico=False)
        except EntradaInvalida:
            pass
        else:
            raise AssertionError(a)


def test_restricoes_excluidas_e_sem_comprador():
    r, _ = _t(recomendar, T, restricoes={"culturas_excluidas": ["trigo"], "sem_comprador": ["milho", "aveia_grao"]}, incluir_diagnostico=False)
    el = {e["id"]: e["motivos"] for e in r["eliminadas"]}
    assert el["soja__trigo"] == ["Excluída pelo produtor."]  # slug antigo = soja__trigo; milho_verao__trigo segue valendo
    assert el["milho_verao__trigo"] == ["Sem comprador local informado pelo produtor (milho)."]  # a exclusão antiga só vale p/ soja no verão
    assert "Sem comprador local informado pelo produtor" in el["soja__milho_safrinha"][0] and "soja__milho_braquiaria" in el
    assert "Sem comprador local informado pelo produtor (milho)" in el["milho_verao__aveia"][0]  # verão em milho também precisa de comprador
    assert [x["id"] for x in r["ranking"]][:3] == ["soja__milheto_crotalaria", "soja__aveia_nabo", "soja__aveia"]
    assert r["atual"]["eliminada"] and r["entrada"]["restricoes"]["sem_comprador"] == ["milho", "aveia_grao"]
    assert r["entrada"]["restricoes"]["culturas_excluidas"] == ["soja__trigo"]
    r2, _ = _t(recomendar, T, restricoes={"sem_comprador": ["trigo"]}, incluir_diagnostico=False)
    assert {e["id"] for e in r2["eliminadas"]} >= {"soja__soja_safrinha", "soja__trigo", "milho_verao__trigo"}
    # tudo eliminado -> EntradaInvalida
    try:
        recomendar(T, restricoes={"culturas_excluidas": [i for i in opcoes()["rotacoes"] for i in [i["id"]]]})
    except EntradaInvalida:
        pass
    else:
        raise AssertionError("todas eliminadas")


def test_restricoes_maquinas():
    base, _ = _t(recomendar, T, incluir_diagnostico=False)
    r, _ = _t(recomendar, T, restricoes={"maquinas": {"plataforma_milho": False, "semeadora_consorcio": False}}, incluir_diagnostico=False)
    rb, rr = _rk(base), _rk(r)
    assert "milho_safrinha" in rr and "milho_braquiaria" in rr  # não elimina
    assert "milho_verao__aveia" in rr
    assert any("plataforma de milho" in a for a in rr["milho_safrinha"]["card"]["avisos"])
    assert any("semeadora de consórcio" in a for a in rr["milho_braquiaria"]["card"]["avisos"])
    assert rr["milho_safrinha"]["margem"]["total_r_ha"] == rb["milho_safrinha"]["margem"]["total_r_ha"] - 250
    assert rr["milho_verao__aveia"]["margem"]["total_r_ha"] == rb["milho_verao__aveia"]["margem"]["total_r_ha"] - 250  # colheita do milho verão
    assert rr["milho_braquiaria"]["margem"]["total_r_ha"] == rb["milho_braquiaria"]["margem"]["total_r_ha"] - 330
    assert rr["trigo"]["margem"] == rb["trigo"]["margem"] and not any("terceirizar" in a for a in rr["trigo"]["card"]["avisos"])
    # máquina true / omitida = tem
    r_ok, _ = _t(recomendar, T, restricoes={"maquinas": {"plataforma_milho": True}}, incluir_diagnostico=False)
    assert _antigas(r_ok) == ESPERADO


def test_mercado_no_card():
    r, _ = _t(recomendar, T, incluir_diagnostico=False)
    m = {k: v["card"]["mercado"] for k, v in _rk(r).items()}
    assert m["milho_safrinha"]["nivel"] == "alto" and m["trigo"]["nivel"] == "médio" and m["aveia"]["nivel"] == "não se aplica"
    assert any(e.startswith("Mercado no Oeste do PR: alto") for e in _rk(r)["milho_safrinha"]["card"]["evidencias"])


def test_irrigacao():
    base, _ = _t(recomendar, T, incluir_diagnostico=False)
    r, _ = _t(recomendar, T, irrigacao={"disponivel": True}, incluir_diagnostico=False)
    rb, rr = _rk(base), _rk(r)
    for k in ("milho_safrinha", "milho_braquiaria", "trigo", "soja__sorgo", "soja__feijao_safrinha"):
        assert rr[k]["criterios"]["agua"] >= rb[k]["criterios"]["agua"] and rr[k]["irrigacao"]["lamina_media_mm_ano"] > 0
        assert rr[k]["margem"]["total_r_ha"] < rb[k]["margem"]["total_r_ha"]
        assert any(e.startswith("Irrigado: lâmina média") for e in rr[k]["card"]["evidencias"])
    assert rr["milho_safrinha"]["criterios"]["risco"] > rb["milho_safrinha"]["criterios"]["risco"]  # sem veranico
    assert rr["trigo"]["criterios"]["risco"] == rb["trigo"]["criterios"]["risco"]  # trigo só tem geada
    for k in ("aveia", "milheto_crotalaria", "pousio", "nabo_forrageiro"):  # cobertura/pousio: não irriga
        k = k if k in rr else f"soja__{k}"
        assert "irrigacao" not in rr[k] and rr[k]["criterios"] == rb[k]["criterios"]
    # disponivel=False = sequeiro; custo maior aumenta o desconto
    r0, _ = _t(recomendar, T, irrigacao={"disponivel": False}, incluir_diagnostico=False)
    assert _antigas(r0) == ESPERADO
    r2, _ = _t(recomendar, T, irrigacao={"disponivel": True, "custo_r_mm_ha": 8, "lamina_max_mm_dia": 3}, incluir_diagnostico=False)
    ir2 = _rk(r2)["milho_safrinha"]["irrigacao"]
    assert abs(ir2["custo_r_ha"] - 8 * ir2["lamina_media_mm_ano"]) < 1 and r2["entrada"]["irrigacao"]["lamina_max_mm_dia"] == 3


def test_entradas_novas_invalidas():
    for kw in [dict(restricoes={"culturas_excluidas": ["arroz"]}), dict(restricoes={"sem_comprador": ["soja"]}),
               dict(restricoes={"maquinas": {"trator": True}}), dict(restricoes={"maquinas": {"plataforma_milho": "sim"}}),
               dict(restricoes={"x": 1}), dict(irrigacao={}), dict(irrigacao={"disponivel": "sim"}),
               dict(irrigacao={"disponivel": True, "lamina_max_mm_dia": 0}), dict(irrigacao={"disponivel": True, "custo_r_mm_ha": -1}),
               dict(ajustes={"produtividade": {"soja": 0}}), dict(ajustes={"produtividade": {"arroz": 5}}),
               dict(ajustes={"produtividade": {"milho": 100, "milho_2safra": 90}}), dict(ajustes={"produtividade": {"soja": "x"}})]:
        try:
            recomendar(T, incluir_diagnostico=False, **kw)
        except EntradaInvalida:
            pass
        else:
            raise AssertionError(kw)


if __name__ == "__main__":
    t0 = time.perf_counter()
    test_talhao_72638()
    print("frio total", round(time.perf_counter() - t0, 2))
    test_poligono_cascavel(); test_ponto_guaira(); test_erros(); test_opcoes_e_atual_eliminada()
    from field_shift.motor import aquecer
    t0 = time.perf_counter(); aquecer(); print("aquecer (ja quente)", round(time.perf_counter() - t0, 2))
    t0 = time.perf_counter(); recomendar({"lat": -24.5, "lon": -53.9}); print("quente, ponto novo", round(time.perf_counter() - t0, 2))
    print("TUDO OK")


def test_empate_tecnico():
    # 15/03: millet/crotalaria and corn + brachiaria are less than 0.02 apart on field 72638
    r = recomendar({"talhao_id": "72638"}, semeadura_safrinha="15/03", incluir_diagnostico=False)
    e = r["agora"]["empate_tecnico"]
    assert e is not None and e["ids"][:2] == ["soja__milheto_crotalaria", "soja__milho_braquiaria"] and 0 <= e["diferenca"] < 0.02
    tied = [x for x in r["agora"]["ranking"] if x["id"] in e["ids"]]
    assert all(x["card"]["avisos"][0].startswith("Empate técnico") for x in tied)
    assert not any(a.startswith("Empate técnico") for x in r["agora"]["ranking"] if x["id"] not in e["ids"] for a in x["card"]["avisos"])
    # 15/01: corn + brachiaria clearly ahead
    assert recomendar({"talhao_id": "72638"}, semeadura_safrinha="15/01", incluir_diagnostico=False)["agora"]["empate_tecnico"] is None
