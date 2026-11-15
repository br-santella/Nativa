"""Summer-crop stage -> estimated harvest -> 2nd-window sowing; `agora`/`proxima_safra` blocks; `ganho_vs_atual`.
Uses the real service and the data in data/ (run: uv run pytest tests/test_crop_calendar.py)."""
from local_data import needs_data
from datetime import date

import pytest

from field_shift import crop_calendar as cal
from field_shift.core import InvalidInput, options, recommend

T = {"talhao_id": "72638"}
SOYBEAN = "soja__milho_safrinha"
REF = "2026-12-01"


def _rec(**kw):
    kw.setdefault("include_diagnosis", False)
    kw.setdefault("current_rotation", SOYBEAN)
    return recommend(T, **kw)


def _ids(block):
    return [x["id"] for x in block["ranking"]]


def _eliminated(block):
    return {e["id"]: e["motivos"] for e in block["eliminadas"]}


# Pure calendar
def test_stage_days():
    assert [e["dias"] for e in cal.STAGES["soja"].values()] == [90, 65, 48, 32, 10, 0]
    assert list(cal.STAGES["milho_verao"]) == ["vegetativo", "pendoamento", "grao_leitoso", "grao_farinaceo", "maturacao", "colhida"]
    assert list(cal.STAGES["milho_verao"].values())[-1]["dias"] == 0


@pytest.mark.parametrize("stage,ref,harvest,sowing,late", [
    ("enchimento_graos", "2026-12-01", "02/01", "15/01", False),
    ("floracao", "2026-12-01", "04/02", "15/02", False),
    ("vegetativo", "2026-12-01", "01/03", "01/03", False),
    ("vegetativo", "2026-12-20", "20/03", None, True),   # after the last sowing (15/03)
    ("colhida", "2027-02-01", "01/02", "01/02", False),  # harvested: harvest = reference
    ("colhida", "2026-11-14", "14/11", "15/01", False),
])
def test_stage_to_harvest_and_sowing(stage, ref, harvest, sowing, late):
    r = cal.resolver("soja", stage, None, date.fromisoformat(ref))
    assert (r["colheita"], r["semeadura_2a"], r["tarde_demais"], r["origem"]) == (harvest, sowing, late, "estagio")


def test_precedence_and_given_sowing():
    ref = date(2026, 12, 1)
    r = cal.resolver("soja", "vegetativo", "20/01", ref)  # colheita_prevista overrides the stage
    assert (r["origem"], r["colheita"], r["semeadura_2a"], r["dias_ate_colheita"]) == ("informada", "20/01", "01/02", 50)
    assert cal.resolver("soja", "enchimento_graos", None, ref, "01/03")["semeadura_2a"] == "01/03"  # informada vence a derivada
    assert cal.resolver("soja", None, None, ref) is None  # premissa
    with pytest.raises(ValueError, match="anterior à colheita"):
        cal.resolver("soja", "floracao", None, ref, "15/01")  # colheita ~04/02


@pytest.mark.parametrize("summer,stage", [("soja", "pendoamento"), ("milho_verao", "enchimento_graos"), ("soja", "xyz")])
def test_incompatible_stage(summer, stage):
    with pytest.raises(ValueError, match="estagio_verao"):
        cal.resolver(summer, stage, None, date(2026, 12, 1))


@pytest.mark.parametrize("x", ["2026-01-10", "31/02", "1/1", "x"])
def test_invalid_expected_harvest(x):
    with pytest.raises(ValueError, match="colheita_prevista"):
        cal.resolver("soja", None, x, date(2026, 12, 1))


# Exemplo principal
@needs_data
def test_soy_grain_fill_field_72638():
    r = _rec(summer_stage="enchimento_graos", reference_date=REF)
    assert r["cultura_atual"] == {"id": "soja", "nome": "Soja"}
    assert r["estagio_verao"]["id"] == "enchimento_graos" and r["estagio_verao"]["dias_tipicos_ate_colheita"] == 32
    assert "validar com Embrapa" in r["estagio_verao"]["fonte"]
    assert r["colheita_estimada"] == {"data": "02/01", "origem": "estagio"}
    assert r["semeadura_2a"] == {"data": "15/01", "origem": "derivada"} and r["dias_ate_colheita"] == 32
    assert r["entrada"]["semeadura_safrinha"] == "15/01" and r["entrada"]["data_referencia"] == REF
    assert not r["avisos"]
    # `agora`: summer soybean only; `proxima_safra`: summer corn only; ranking and alternatives are aliases of `agora`
    assert all(i.startswith("soja__") for i in _ids(r["agora"])) and all(i.startswith("milho_verao__") for i in _ids(r["proxima_safra"]))
    assert r["ranking"] == r["agora"]["ranking"] and r["alternativas"] == r["agora"]["alternativas"]
    assert [x["posicao"] for x in r["agora"]["ranking"]] == list(range(1, len(r["agora"]["ranking"]) + 1))
    assert [x["posicao"] for x in r["proxima_safra"]["ranking"]][0] == 1
    assert r["atual"]["id"] == SOYBEAN and r["atual"]["atual"] and r["atual"]["posicao"] is not None
    assert [x["id"] for x in r["eliminadas"]] == [x["id"] for x in r["agora"]["eliminadas"] + r["proxima_safra"]["eliminadas"]]
    assert "soja__soja_safrinha" in _eliminated(r["agora"])
    # with sowing on 15/01, summer corn (typical harvest 05/02) does not allow second-season corn in the next season
    assert any("colheita de milho verão" in m for m in _eliminated(r["proxima_safra"])["milho_verao__milho_safrinha"])


@needs_data
def test_gain_vs_current():
    r = _rec(summer_stage="enchimento_graos", reference_date=REF)
    by_id = {x["id"]: x for x in r["agora"]["ranking"] + r["proxima_safra"]["ranking"]}
    assert by_id[SOYBEAN]["ganho_vs_atual"] is None  # the current one itself
    g = by_id["soja__milho_braquiaria"]["ganho_vs_atual"]
    assert g["comparado_com"] == SOYBEAN
    assert g["soja_seguinte_sc"] == 2.0  # bonus 3.0 (corn + brachiaria) − 1.0 (second-season corn)
    assert g["soja_seguinte_sc_faixa"] == [2.0, 2.0]  # for now range = central value
    assert g["soja_seguinte_rs"] == pytest.approx(2.0 * g["preco_soja_r_sc"], abs=1)
    assert "validar com agrônomo/Embrapa" in g["fonte"]
    assert g["renda_2a_safra"]["origem"].startswith("dado:") and g["agua"]["origem"].startswith("dado:")
    assert g["solo"]["dias_descobertos"] == 30 - 60 and g["solo"]["cobertura"] == 0.3
    # same summer: total margin = extra income of the 2nd season + value of the bonus in the following soybean
    assert g["margem_total"]["r_ha"] == pytest.approx(g["renda_2a_safra"]["r_ha"] + g["soja_seguinte_rs"], abs=2)
    # a cover crop loses income but gains soil; the other summer also brings a gain (summer corn: +3 bags/ha of summer bonus)
    c = by_id["soja__aveia"]["ganho_vs_atual"]
    assert c["renda_2a_safra"]["r_ha"] < 0 and c["solo"]["dias_descobertos"] == 40 - 60 and c["soja_seguinte_sc"] == 1.0
    p = by_id["milho_verao__aveia"]["ganho_vs_atual"]
    assert p["soja_seguinte_sc"] == 4.0 and p["comparado_com"] == SOYBEAN
    assert all(x["ganho_vs_atual"] for x in r["proxima_safra"]["ranking"])


@needs_data
def test_current_summer_corn_uses_farmer_harvest():
    base = _rec(current_rotation="milho_verao__milho_safrinha", sowing_second="01/02")  # premissa: colheita 05/02 > 01/02
    assert any("05/02" in m for m in _eliminated(base["agora"])["milho_verao__milho_safrinha"])
    assert base["colheita_estimada"] == {"data": "05/02", "origem": "premissa"} and base["atual"]["eliminada"]
    r = _rec(current_rotation="milho_verao__milho_safrinha", summer_stage="grao_leitoso", reference_date=REF)  # 60 d -> 30/01
    assert r["colheita_estimada"]["data"] == "30/01" and r["semeadura_2a"]["data"] == "01/02"
    assert "milho_verao__milho_safrinha" in _ids(r["agora"]) and r["atual"]["posicao"] is not None
    assert all(i.startswith("milho_verao__") for i in _ids(r["agora"])) and all(i.startswith("soja__") for i in _ids(r["proxima_safra"]))
    assert r["cultura_atual"]["id"] == "milho_verao"


# Colheita tarde demais
@needs_data
def test_too_late_harvest_eliminates_only_sowing_followers():
    r = _rec(summer_stage="vegetativo", reference_date="2026-12-20")  # colheita ~20/03
    assert r["colheita_estimada"] == {"data": "20/03", "origem": "estagio"} and r["semeadura_2a"] is None
    assert any("tarde demais para a safrinha" in a for a in r["avisos"])
    el = _eliminated(r["agora"])
    for sec_ in ("milho_safrinha", "milho_braquiaria", "sorgo", "feijao_safrinha", "milheto_crotalaria"):
        assert any("tarde demais para a safrinha" in m for m in el[f"soja__{sec_}"]), sec_
    assert {"trigo", "aveia", "nabo_forrageiro", "aveia_nabo", "pousio"} == {i.split("__")[1] for i in _ids(r["agora"])}
    assert r["atual"]["eliminada"] and r["atual"]["posicao"] is None and r["atual"]["nota"] is None
    assert all(x["ganho_vs_atual"] is None for x in r["agora"]["ranking"])  # without the current one, nothing to compare


# Precedence and inputs
@needs_data
def test_expected_harvest_beats_stage_and_sowing_beats_derived():
    r = _rec(summer_stage="vegetativo", expected_harvest="20/01", reference_date=REF)
    assert r["colheita_estimada"] == {"data": "20/01", "origem": "informada"} and r["dias_ate_colheita"] == 50
    assert r["semeadura_2a"] == {"data": "01/02", "origem": "derivada"} and r["estagio_verao"]["id"] == "vegetativo"
    assert any("vale a colheita_prevista" in a for a in r["avisos"])
    r = _rec(summer_stage="enchimento_graos", reference_date=REF, sowing_second="01/03")
    assert r["semeadura_2a"] == {"data": "01/03", "origem": "informada"} and r["colheita_estimada"]["data"] == "02/01"
    assert r["entrada"]["semeadura_safrinha"] == "01/03" and any("01/03 informada" in a for a in r["avisos"])


@needs_data
def test_no_stage_nor_harvest_uses_assumption_and_warns():
    r = _rec()
    assert r["colheita_estimada"] == {"data": "10/01", "origem": "premissa"} and r["dias_ate_colheita"] is None
    assert r["semeadura_2a"] == {"data": "01/02", "origem": "premissa"} and r["estagio_verao"] is None
    assert any("Sem estagio_verao nem colheita_prevista" in a and "premissa" in a for a in r["avisos"])
    r = _rec(sowing_second="15/02")
    assert r["semeadura_2a"] == {"data": "15/02", "origem": "informada"} and r["colheita_estimada"]["origem"] == "premissa"


def test_invalid_inputs():
    with pytest.raises(InvalidInput, match="rotacao_atual"):
        recommend(T, include_diagnosis=False)
    with pytest.raises(InvalidInput, match="estagio_verao"):
        _rec(summer_stage="pendoamento")
    with pytest.raises(InvalidInput, match="anterior à colheita"):
        _rec(summer_stage="floracao", reference_date=REF, sowing_second="15/01")
    with pytest.raises(InvalidInput, match="anterior à colheita"):
        _rec(expected_harvest="20/02", sowing_second="01/02")
    with pytest.raises(InvalidInput, match="data_referencia"):
        _rec(reference_date="amanhã")
    with pytest.raises(InvalidInput, match="colheita_prevista"):
        _rec(expected_harvest="2027-01-20")


# `rotacoes` split into the blocks
@needs_data
def test_rotations_land_in_the_right_block():
    requested = [{"verao": "soja", "segunda": "milho_safrinha"}, {"verao": "soja", "segunda": "aveia"}, {"verao": "soja", "segunda": "soja_safrinha"},
               {"verao": "milho_verao", "segunda": "aveia_nabo"}, {"verao": "milho_verao", "segunda": "milho_safrinha"}]
    r = _rec(summer_stage="enchimento_graos", reference_date=REF, rotations=requested)
    assert set(_ids(r["agora"])) == {SOYBEAN, "soja__aveia"} and set(_eliminated(r["agora"])) == {"soja__soja_safrinha"}
    assert _ids(r["proxima_safra"]) == ["milho_verao__aveia_nabo"] and set(_eliminated(r["proxima_safra"])) == {"milho_verao__milho_safrinha"}
    assert r["proxima_safra"]["ranking"][0]["ganho_vs_atual"]
    # current one outside `rotacoes`: it does not show up, but the gain is still computed against it
    r = _rec(summer_stage="enchimento_graos", reference_date=REF, rotations=[{"verao": "milho_verao", "segunda": "aveia_nabo"}])
    assert r["agora"]["ranking"] == [] and r["atual"]["avaliada"] is False
    assert r["proxima_safra"]["ranking"][0]["ganho_vs_atual"]["comparado_com"] == SOYBEAN


# /v1/opcoes
@needs_data
def test_options_stages():
    o = {c["id"]: c for c in options()["culturas_verao"]}
    assert [(e["id"], e["dias_ate_colheita"]) for e in o["soja"]["estagios"]] == [
        ("vegetativo", 90), ("floracao", 65), ("formacao_vagens", 48), ("enchimento_graos", 32), ("maturacao", 10), ("colhida", 0)]
    assert [e["id"] for e in o["milho_verao"]["estagios"]][1] == "pendoamento" and o["milho_verao"]["estagios"][-1]["dias_ate_colheita"] == 0
    assert "Embrapa" in options()["estagios_fonte"]
