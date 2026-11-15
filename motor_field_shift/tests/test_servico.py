"""Testes da camada de serviço (rodar: uv run python tests/test_servico.py  ou  uv run pytest tests/test_servico.py)."""
import json
import time

from field_shift.motor import EntradaInvalida, ForaDaRegiao, diagnosticar, opcoes, recomendar

ESPERADO = {"milho_braquiaria": 0.814, "milho_safrinha": 0.757, "milheto_crotalaria": 0.756, "aveia": 0.698, "pousio": 0.547, "trigo": 0.466}


def _t(f, *a, **k):
    t0 = time.perf_counter()
    r = f(*a, **k)
    json.dumps(r, allow_nan=False)
    return r, time.perf_counter() - t0


def test_talhao_72638():
    r, dt = _t(recomendar, {"talhao_id": "72638"})
    assert {x["id"]: x["nota"] for x in r["ranking"]} == ESPERADO
    assert r["entrada"]["rotacao_atual"] == "milho_safrinha" and r["atual"]["atual"]
    assert [a["id"] for a in r["alternativas"]] == ["milho_braquiaria", "milheto_crotalaria", "aveia"]
    assert [e["id"] for e in r["eliminadas"]] == ["soja_safrinha"]
    # margem incremental e escala S (soja de Cascavel); saída arredondada (R$ sem casas, critérios com 3)
    m = {x["id"]: x["margem"] for x in r["ranking"]}
    assert m["milho_safrinha"]["incremental_r_ha"] == 993 and m["milho_braquiaria"]["incremental_r_ha"] == 1033
    assert m["trigo"]["escala_S_r_ha"] == 1083 and m["trigo"]["total_r_ha"] == m["trigo"]["total_r_ha"] // 1
    assert r["ranking"][0]["criterios"]["renda"] == 0.977 and r["ranking"][5]["criterios"]["renda"] == 0.0
    # "por quê" comparado com a atual
    top = r["ranking"][0]["card"]["por_que"]
    assert top.startswith("Em relação à atual (milho safrinha):") and "R$ 1.033/ha contra R$ 993/ha" in top
    atual = r["atual"]["card"]["por_que"]
    assert atual.startswith("É a rotação atual; ficou em 2º lugar entre 6 opções válidas. A melhor alternativa (milho safrinha + braquiária)")
    print("72638", round(dt, 2), "s", [(x["id"], round(x["nota"], 2)) for x in r["ranking"]])


def test_poligono_cascavel():
    # ~100 ha em lavoura a ~15 km a leste de Cascavel (conferido no MapBiomas pelo diagnóstico)
    lon, lat, h = -53.30, -24.90, 0.0045
    g = {"type": "Polygon", "coordinates": [[[lon - h, lat - h], [lon + h, lat - h], [lon + h, lat + h], [lon - h, lat + h], [lon - h, lat - h]]]}
    r, dt = _t(recomendar, {"geometry": {"type": "Feature", "properties": {}, "geometry": g}}, pesos={"renda": 10}, ajustes={"precos": {"soja": 100}, "custos": {"milho": 4000}, "linha_custo": "cot"})
    d = r["diagnostico"]
    print("poligono", round(dt, 2), "s", d["area"]["area_ha"], d["area"]["municipio"], [(h["ano"], h["nome_classe"]) for h in d["historico"][-3:]], d["avisos"])
    assert d["area"]["origem"] == "geometry" and r["entrada"]["rotacao_atual"] == "milho_safrinha"
    assert any("assumida" in a for a in r["avisos"])
    return r


def test_ponto_guaira():
    r, dt = _t(recomendar, {"lat": -24.20, "lon": -54.20}, n_alternativas=2, incluir_diagnostico=False)
    assert len(r["alternativas"]) == 2 and "diagnostico" not in r
    d, dt2 = _t(diagnosticar, {"lat": -24.20, "lon": -54.20})
    print("ponto Guaíra", round(dt, 2), d["area"]["area_ha"], d["area"]["municipio"], [(h["ano"], h["nome_classe"]) for h in d["historico"][-3:]], d["avisos"])


def test_erros():
    for a, exc in [({"lat": -25.43, "lon": -49.27}, ForaDaRegiao), ({"talhao_id": "x"}, EntradaInvalida), ({}, EntradaInvalida),
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
    assert o["regiao"]["n_municipios"] == 50 and o["talhoes_demo"][0]["id"] == "72638"
    r, _ = _t(recomendar, {"talhao_id": "72638"}, rotacao_atual="soja_safrinha", incluir_diagnostico=False)
    assert r["atual"]["eliminada"] and not any(x["atual"] for x in r["ranking"])


if __name__ == "__main__":
    t0 = time.perf_counter()
    test_talhao_72638()
    print("frio total", round(time.perf_counter() - t0, 2))
    test_poligono_cascavel(); test_ponto_guaira(); test_erros(); test_opcoes_e_atual_eliminada()
    from field_shift.motor import aquecer
    t0 = time.perf_counter(); aquecer(); print("aquecer (ja quente)", round(time.perf_counter() - t0, 2))
    t0 = time.perf_counter(); recomendar({"lat": -24.5, "lon": -53.9}); print("quente, ponto novo", round(time.perf_counter() - t0, 2))
    print("TUDO OK")
