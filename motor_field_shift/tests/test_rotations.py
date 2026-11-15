"""Rotation = (summer crop, 2nd-window crop): calendar rules, corn on corn, `rotacoes`, old slugs, summer income.
Uses the real service and the data in data/ (run: uv run pytest tests/test_rotations.py)."""
import pytest

from field_shift.app import engine as E
from field_shift.core import InvalidInput, options, recommend

T = {"talhao_id": "72638"}
SOYBEAN_CORN = {"verao": "soja", "segunda": "milho_safrinha"}


def _rec(**kw):
    kw.setdefault("include_diagnosis", False)
    kw.setdefault("current_rotation", "soja__milho_safrinha")
    return recommend(T, **kw)


def _by_id(r):
    return {x["id"]: x for x in r["agora"]["ranking"] + r["proxima_safra"]["ranking"]}  # os dois blocos


def _eliminated(r):
    return {e["id"]: e["motivos"] for e in r["eliminadas"]}


# Calendar and legal rules
@pytest.mark.parametrize("sow_date", E.SOWINGS_2ND)
def test_soy_in_second_window_always_eliminated(sow_date):
    el = _eliminated(_rec(sowing_second=sow_date))
    assert any("Soja sobre soja" in m for m in el["soja__soja_safrinha"])
    assert any("01/09–31/12" in m for m in el["soja__soja_safrinha"])
    # after summer corn it is not soybean on soybean, but the legal soybean sowing window still applies
    assert not any("Soja sobre soja" in m for m in el["milho_verao__soja_safrinha"])
    assert any("01/09–31/12" in m for m in el["milho_verao__soja_safrinha"])
    assert any("vazio sanitário" in m for m in el["milho_verao__soja_safrinha"])


def test_summer_corn_harvest_limits_the_second_crop():
    r = _rec(sowing_second="01/02")
    el = _eliminated(r)
    for sec_ in ("milho_safrinha", "milho_braquiaria", "milheto_crotalaria", "sorgo", "feijao_safrinha"):
        assert any("colheita de milho verão" in m and "01/02" in m for m in el[f"milho_verao__{sec_}"]), sec_
    # wheat, oat, radish and fallow have a fixed date: they do not depend on the summer harvest
    ids = _by_id(r)
    for sec_ in ("trigo", "aveia", "nabo_forrageiro", "aveia_nabo", "pousio"):
        assert f"milho_verao__{sec_}" in ids, sec_
    # (early) soybean allows every 2nd-crop sowing date
    assert "soja__milho_safrinha" in ids
    ok = _by_id(_rec(sowing_second="01/03"))
    assert "milho_verao__milho_safrinha" in ok and "milho_verao__sorgo" in ok


def test_second_season_bean_window():
    el = _eliminated(_rec(sowing_second="01/03"))
    assert any("fora da janela de feijão safrinha" in m for m in el["soja__feijao_safrinha"])
    assert "soja__feijao_safrinha" in _by_id(_rec(sowing_second="15/02"))
    assert "soja__sorgo" in _by_id(_rec(sowing_second="15/03"))


def test_valid_sowings_in_options():
    c = {x["id"]: x for x in options()["combinacoes"]}
    assert c["soja__soja_safrinha"]["valida"] is False and c["soja__soja_safrinha"]["semeaduras_validas"] == []
    assert c["milho_verao__soja_safrinha"]["valida"] is False
    assert c["milho_verao__milho_safrinha"]["semeaduras_validas"] == ["15/02", "01/03", "15/03"]
    assert c["soja__milho_safrinha"]["semeaduras_validas"] == E.SOWINGS_2ND
    assert c["soja__feijao_safrinha"]["semeaduras_validas"] == ["15/01", "01/02", "15/02"]
    assert c["soja__milho_safrinha"]["id_legado"] == "milho_safrinha" and "id_legado" not in c["soja__sorgo"]


# Milho sobre milho
def test_corn_on_corn_penalizes_and_does_not_eliminate():
    r = _rec(sowing_second="01/03")
    ids = _by_id(r)
    mm, sm = ids["milho_verao__milho_safrinha"], ids["soja__milho_safrinha"]
    assert "milho_verao__milho_safrinha" not in _eliminated(r)
    assert sm["criterios"]["pragas"] == 0.5 and mm["criterios"]["pragas"] == pytest.approx(0.25)
    assert ids["milho_verao__milho_braquiaria"]["criterios"]["pragas"] == pytest.approx(0.40)
    assert any("cigarrinha" in x and "enfezamento" in x for x in mm["card"]["riscos"])
    assert any("0.25" in x and "cigarrinha" in x for x in mm["card"]["evidencias"])
    # other crops after summer corn do not get the penalty
    assert ids["milho_verao__sorgo"]["criterios"]["pragas"] == ids["soja__sorgo"]["criterios"]["pragas"]
    assert not any("cigarrinha" in x for x in ids["soja__milho_safrinha"]["card"]["riscos"])


# Rotation benefit and summer income
def test_summer_corn_income():
    r = _rec(sowing_second="01/03", rotations=[SOYBEAN_CORN, {"verao": "milho_verao", "segunda": "aveia"}, {"verao": "soja", "segunda": "aveia"}])
    ids = _by_id(r)
    mv, sa, sv = ids["milho_verao__aveia"]["margem"], ids["soja__aveia"]["margem"], ids["soja__milho_safrinha"]["margem"]
    soy, corn1 = sa["itens"][0], mv["itens"][0]
    assert soy["cultura"] == "Soja" and corn1["cultura"] == "Milho verão (1ª safra)"
    assert "milho 1ª safra" not in corn1["fonte"] and "IBGE PAM" in corn1["fonte"] and "Ponta Grossa-PR" in corn1["fonte"]
    assert "SEAB/DERAL" in corn1["fonte"]
    # same S scale (municipality soybean margin): incomes comparable between summer soybean and summer corn
    assert mv["escala_S_r_ha"] == sa["escala_S_r_ha"] == sv["escala_S_r_ha"]
    # incremental = (summer corn − soybean) + oat + bonus (oat 2 + summer corn 3 bags/ha × soybean price)
    expected = (corn1["margem_r_ha"] - soy["margem_r_ha"]) + (mv["itens"][1]["margem_r_ha"]) + mv["bonus_proxima_soja_r_ha"]
    assert mv["incremental_r_ha"] == pytest.approx(expected, abs=2)
    assert mv["bonus_proxima_soja_r_ha"] - sa["bonus_proxima_soja_r_ha"] == pytest.approx(3.0 * 120.14, abs=2)  # +3 bags/ha from the catalog
    c = ids["milho_verao__aveia"]["card"]
    assert any("quebra ciclo de doença e nematoide" in b for b in c["beneficios"])
    assert any("Bônus na soja seguinte: 5 sc/ha" in e for e in c["evidencias"])


def test_summer_soy_keeps_old_scores():
    all_ = _rec(sowing_second="01/02")
    old = {x["id"]: x["nota"] for x in all_["ranking"] if "id_legado" in x}
    assert old == {f"soja__{k}": v for k, v in {"milho_braquiaria": 0.795, "milho_safrinha": 0.747, "milheto_crotalaria": 0.757,
                                                     "aveia": 0.7, "pousio": 0.57, "trigo": 0.524}.items()}


# Culturas novas
def test_new_crops_have_water_income_and_source():
    r = _rec(sowing_second="15/02")
    ids = _by_id(r)
    for sec_ in ("sorgo", "feijao_safrinha", "nabo_forrageiro", "aveia_nabo"):
        x = ids[f"soja__{sec_}"]
        assert 0 < x["criterios"]["agua"] <= 1 and 0 <= x["criterios"]["renda"] <= 1
        assert any(e.startswith("Água: na fase crítica") for e in x["card"]["evidencias"]), sec_
    sorghum = ids["soja__sorgo"]["margem"]["itens"][1]
    assert sorghum["cultura"] == "Sorgo" and "estimativa — validar" in sorghum["fonte"] and sorghum["rendimento_sc_ha"] > 0
    beans = ids["soja__feijao_safrinha"]["margem"]["itens"][1]
    assert "SEAB/DERAL" in beans["fonte"] and "Francisco Beltrão" in beans["fonte"]
    for sec_ in ("nabo_forrageiro", "aveia_nabo"):  # cobertura: renda = −custo
        item = ids[f"soja__{sec_}"]["margem"]["itens"][1]
        assert item["rendimento_sc_ha"] is None and item["margem_r_ha"] < 0 and "estimativa" in item["fonte"]


def test_new_crops_in_farmer_inputs():
    r = _rec(sowing_second="15/02", adjustments={"precos": {"sorgo": 60, "feijao": 250}, "custos": {"sorgo": 2000, "feijao": 4000, "milho_verao": 6000},
                                                  "produtividade": {"sorgo": 70, "feijao": 30, "milho_verao": 160}},
             rotations=[{"verao": "milho_verao", "segunda": "sorgo"}, {"verao": "soja", "segunda": "feijao_safrinha"}])
    ids = _by_id(r)
    assert ids["milho_verao__sorgo"]["margem"]["itens"][0]["rendimento_sc_ha"] == 160
    assert ids["milho_verao__sorgo"]["margem"]["itens"][1]["margem_r_ha"] == 70 * 60 - 2000
    assert ids["soja__feijao_safrinha"]["margem"]["itens"][1]["margem_r_ha"] == 30 * 250 - 4000
    with pytest.raises(InvalidInput):
        _rec(adjustments={"produtividade": {"milho_verao": 100, "milho_1safra": 100}})


def test_no_buyer_for_sorghum_and_beans():
    el = _eliminated(_rec(sowing_second="15/02", constraints={"sem_comprador": ["sorgo", "feijao"]}))
    assert "Sem comprador local informado pelo produtor (sorgo)" in el["soja__sorgo"][0]
    assert "Sem comprador local informado pelo produtor (feijao)" in el["milho_verao__feijao_safrinha"][0]


# `rotacoes` input
def test_rotations_evaluates_only_requested():
    requested = [{"verao": "milho_verao", "segunda": "aveia_nabo"}, SOYBEAN_CORN, {"verao": "soja", "segunda": "sorgo"},
               {"verao": "soja", "segunda": "soja_safrinha"}, {"verao": "milho_verao", "segunda": "milho_safrinha"}]
    r = _rec(rotations=requested)  # default sowing 01/02: summer corn → second-season corn is eliminated by the harvest
    assert set(_by_id(r)) == {"milho_verao__aveia_nabo", "soja__milho_safrinha", "soja__sorgo"}
    assert set(_eliminated(r)) == {"soja__soja_safrinha", "milho_verao__milho_safrinha"}  # eliminated = a result, not an error
    assert r["entrada"]["rotacoes"] == requested
    assert r["atual"]["id"] == "soja__milho_safrinha" and r["atual"]["atual"]
    # the score does not depend on the other evaluated rotations
    all_ = _by_id(_rec())
    assert {k: v["nota"] for k, v in _by_id(r).items()} == {k: all_[k]["nota"] for k in _by_id(r)}
    # without `rotacoes`, the whole catalog is evaluated
    assert len(all_) + len(_eliminated(_rec())) == len(E.CATALOG) == 22
    assert "rotacoes" not in _rec()["entrada"]


def test_rotations_only_eliminated_is_not_error():
    r = _rec(rotations=[{"verao": "soja", "segunda": "soja_safrinha"}], current_rotation="milho_verao__aveia")
    assert r["ranking"] == [] and r["alternativas"] == [] and set(_eliminated(r)) == {"soja__soja_safrinha"}
    assert r["atual"]["avaliada"] is False and any("eliminadas" in a for a in r["avisos"])


def test_rotations_current_outside_selection():
    r = _rec(rotations=[{"verao": "soja", "segunda": "sorgo"}], current_rotation="milho_safrinha")
    assert r["atual"]["id"] == "soja__milho_safrinha" and r["atual"]["avaliada"] is False
    assert [x["id"] for x in r["alternativas"]] == ["soja__sorgo"]
    assert "Em relação à atual" not in r["ranking"][0]["card"]["por_que"]


@pytest.mark.parametrize("rotations", [
    [], [SOYBEAN_CORN, SOYBEAN_CORN], [{"verao": "soja", "segunda": "girassol"}], [{"verao": "trigo", "segunda": "pousio"}],
    [{"verao": "soja"}], [{"verao": "soja", "segunda": "pousio", "x": 1}], ["soja__pousio"], "soja__pousio",
])
def test_invalid_rotations(rotations):
    with pytest.raises(InvalidInput):
        _rec(rotations=rotations)


# Slugs antigos e ids
def test_old_slugs_equal_new_ids():
    a = _rec(current_rotation="milho_safrinha", constraints={"culturas_excluidas": ["trigo"]})
    b = _rec(current_rotation="soja__milho_safrinha", constraints={"culturas_excluidas": ["soja__trigo"]})
    assert [(x["id"], x["nota"]) for x in a["ranking"]] == [(x["id"], x["nota"]) for x in b["ranking"]]
    assert a["entrada"]["rotacao_atual"] == "soja__milho_safrinha" == b["entrada"]["rotacao_atual"]
    assert {x["id"] for x in a["eliminadas"]} == {x["id"] for x in b["eliminadas"]}
    top = a["ranking"][0]
    assert top["id"] == "soja__milho_braquiaria" and top["id_legado"] == "milho_braquiaria"
    assert top["verao"] == {"id": "soja", "nome": "Soja"} and top["segunda"] == {"id": "milho_braquiaria", "nome": "Milho safrinha + braquiária"}
    for bad in ("milho", "soja__milho", "milho_verao__soja", "x__y"):
        with pytest.raises(InvalidInput):
            _rec(current_rotation=bad)


def test_options_crops_and_combinations():
    o = options()
    assert [c["id"] for c in o["culturas_verao"]] == ["soja", "milho_verao"]
    sec_ = {c["id"]: c for c in o["culturas_segunda"]}
    assert set(sec_) == set(E.SECOND) and len(sec_) == 11
    assert sec_["sorgo"]["tipo"] == "grão" and sec_["aveia_nabo"]["tipo"] == "cobertura" and sec_["nabo_forrageiro"]["tipo"] == "cobertura"
    assert all(c["nome"] and c["descricao_curta"] for c in [*o["culturas_verao"], *sec_.values()])
    assert len(o["combinacoes"]) == 22 and {c["id"] for c in o["combinacoes"]} == set(E.NOME_DE)
    assert {r["id"] for r in o["rotacoes"]} == set(E.NOME_DE)
    sources = {f["item"]: f for f in o["renda_referencia"]["fontes"]}
    assert sources["preço sorgo"]["estimativa"] is True and sources["custo sorgo"]["estimativa"] is True
    assert sources["preço feijao"]["estimativa"] is False and "custo milho_1safra" in sources


def test_p20_never_above_mean():
    """Regression: the bad-year (p20) yield must not exceed the mean yield (same 10-year window for both)."""
    from field_shift.income.income import yields
    for cod in ("4127700", "4104808", "4105805", "4115200"):  # Toledo, Cascavel, Corbelia, Marechal C. Rondon
        for cult, r in yields(cod).items():
            if cult.startswith("_") or r["p20_sc_ha"] is None or r["sc_ha"] is None:
                continue
            assert r["p20_sc_ha"] <= r["sc_ha"], (cod, cult, r)
