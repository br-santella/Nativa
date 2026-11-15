"""Track record of the second crop (field_shift.income.history). Run: uv run pytest tests/test_history.py"""
from field_shift.core import recommend
from field_shift.income import history as H

TOLEDO = "4127700"


def test_track_record_has_last_five_seasons_in_soy_bags():
    tr = H.track_record(TOLEDO, "milho_safrinha")
    assert tr is not None and len(tr["safras"]) == 5
    years = [r["ano"] for r in tr["safras"]]
    assert years == sorted(years) and years[-1] >= 2024
    assert tr["min_sc_soja_ha"] <= tr["media_sc_soja_ha"] <= tr["max_sc_soja_ha"]
    # brachiaria only adds a cost to the same corn
    br = H.track_record(TOLEDO, "milho_braquiaria")
    assert all(b["margem_sc_soja_ha"] < m["margem_sc_soja_ha"] for b, m in zip(br["safras"], tr["safras"]))


def test_no_track_record_for_covers_or_without_municipality():
    assert H.track_record(TOLEDO, "milheto_crotalaria") is None
    assert H.track_record(None, "milho_safrinha") is None


def _by_id(r):
    return {x["id"]: x for x in r["ranking"]}


def test_track_record_drives_income_of_grain_second_crops(monkeypatch):
    a = _by_id(recommend({"talhao_id": "72638"}, current_rotation="soja__milho_safrinha", include_diagnosis=False, n_alternatives=6))
    m = a["soja__milho_safrinha"]["margem"]
    assert m["base_renda"] == "historico" and "historico_renda" in a["soja__milho_safrinha"]
    tr = H.track_record(TOLEDO, "milho_safrinha")
    # incremental for the score = current-price incremental − current corn margin + track-record mean × soybean price
    corn = next(i for i in m["itens"] if i["cultura"] == "Milho 2ª safra")
    soy_price = a["soja__milho_safrinha"]["margem"]["bonus_proxima_soja_r_ha"] / 1.0  # milho_safrinha bonus = 1 sc/ha
    expected = m["incremental_preco_atual_r_ha"] - corn["margem_r_ha"] + tr["media_sc_soja_ha"] * soy_price
    assert abs(m["incremental_r_ha"] - expected) <= 2
    assert any("entra na nota de renda" in e for e in a["soja__milho_safrinha"]["card"]["evidencias"])
    # covers have no track record: their income basis is unchanged
    assert a["soja__milheto_crotalaria"]["margem"]["base_renda"] == "preco_atual"
    assert a["soja__milheto_crotalaria"]["margem"]["incremental_r_ha"] == a["soja__milheto_crotalaria"]["margem"]["incremental_preco_atual_r_ha"]
    # without a track record every candidate falls back to the current-price estimate
    monkeypatch.setattr(H, "track_record", lambda *a, **k: None)
    b = _by_id(recommend({"talhao_id": "72638"}, current_rotation="soja__milho_safrinha", include_diagnosis=False, n_alternatives=6))
    assert all(x["margem"]["base_renda"] == "preco_atual" for x in b.values())
    assert b["soja__milho_safrinha"]["margem"]["incremental_r_ha"] == m["incremental_preco_atual_r_ha"]


def test_farmer_data_keeps_current_price_basis():
    r = _by_id(recommend({"talhao_id": "72638"}, current_rotation="soja__milho_safrinha", include_diagnosis=False, n_alternatives=6,
                          adjustments={"precos": {"milho": 70.0}}))
    m = r["soja__milho_safrinha"]["margem"]
    assert m["base_renda"] == "preco_atual" and m["incremental_r_ha"] == m["incremental_preco_atual_r_ha"]
    assert any("Informativo: não entra na nota" in e for e in r["soja__milho_safrinha"]["card"]["evidencias"])
    # wheat has no farmer data here, so it still uses its track record
    assert r["soja__trigo"]["margem"]["base_renda"] == "historico"


def test_income_score_is_strictly_increasing_and_matches_old_slope_at_zero():
    from field_shift.app.engine import income_score
    s = 1000.0
    xs = [-3000, -1000, -10, 0, 10, 1000, 1500, 3000]
    v = [income_score(x, s) for x in xs]
    assert all(a < b for a, b in zip(v, v[1:])) and 0 < v[0] and v[-1] < 1
    assert income_score(0, s) == 0.5
    assert abs((income_score(10, s) - 0.5) - 10 / (2 * s)) < 1e-6   # same slope as the old linear score near zero


def test_uncertainty_block_in_the_response():
    r = recommend({"talhao_id": "72638"}, current_rotation="soja__milho_safrinha", include_diagnosis=False, n_alternatives=6)
    a = _by_id(r["agora"])
    corn = a["soja__milho_safrinha"]["incerteza"]
    lo, hi = corn["renda"]["faixa_r_ha"]
    assert corn["renda"]["origem"] == "historico" and lo <= corn["renda"]["incremental_r_ha"] <= hi
    n_lo, n_hi = corn["nota_faixa"]
    assert n_lo <= a["soja__milho_safrinha"]["nota"] <= n_hi
    assert len(corn["nota_por_safra"]) == 5 and min(corn["nota_por_safra"].values()) == n_lo
    assert corn["risco_climatico"]["confianca"] == "baixa" and 0 < corn["risco_climatico"]["probabilidade"] < 1
    # cover crop: income is a fixed cost (no range), no climate risk; catalog criteria flagged as estimates
    cov = a["soja__milheto_crotalaria"]["incerteza"]
    assert cov["renda"]["origem"] == "custo_fixo" and cov["renda"]["faixa_r_ha"][0] == cov["renda"]["faixa_r_ha"][1]
    assert cov["risco_climatico"] is None and cov["criterios_estimados"] == ["solo", "pragas"]
    # block stability: wins over the last seasons add up to the number of seasons
    st = r["agora"]["estabilidade"]
    assert sum(p["safras"] for p in st["primeiro"]) == len(st["safras"]) == 5


def test_current_price_basis_reports_bad_year_only():
    r = recommend({"talhao_id": "72638"}, current_rotation="soja__milho_safrinha", include_diagnosis=False, n_alternatives=6,
                   adjustments={"precos": {"milho": 70.0}})
    u = _by_id(r)["soja__milho_safrinha"]["incerteza"]
    assert u["renda"]["origem"] == "ano_ruim_p20" and u["renda"]["faixa_r_ha"][1] is None
    assert u["renda"]["faixa_r_ha"][0] < u["renda"]["incremental_r_ha"] and u["nota_faixa"][1] is None and u["nota_por_safra"] is None
