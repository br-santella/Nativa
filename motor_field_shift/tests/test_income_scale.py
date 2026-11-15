"""Yield-driven cost scaling for summer corn (CONAB sheet built for 12 t/ha vs. the lower municipal PAM yield)."""
import pytest

from field_shift.income import cost_source
from field_shift.income.income import _item, load_reference, yield_cost_factor

REF = load_reference()
SCALE = REF["costs"]["milho_1safra"]["yield_scale"]
BASE_COST = REF["costs"]["milho_1safra"]["coe"]


def _yield(sc_ha, bad=None):
    return {"milho_1safra": dict(sc_ha=sc_ha, cv=0.2, p20_sc_ha=bad, anos="2016-2025")}


def test_scale_block_matches_the_conab_sheet():
    assert SCALE["reference_sc_ha"] == 200.0
    assert SCALE["proportional_r_ha"] == pytest.approx(sum(SCALE["components"].values()))
    assert SCALE["proportional_r_ha"] < BASE_COST  # the split never exceeds the whole variable cost


def test_cost_at_reference_yield_is_unchanged():
    item = _item(REF, {}, _yield(SCALE["reference_sc_ha"]), "milho_1safra")
    assert item["custo"] == pytest.approx(BASE_COST)
    assert item["fator_escala_custo"] == pytest.approx(1.0)


def test_lower_yield_removes_only_the_yield_driven_share():
    item = _item(REF, {}, _yield(140.0), "milho_1safra")
    factor = 140.0 / SCALE["reference_sc_ha"]
    assert item["custo"] == pytest.approx(BASE_COST - SCALE["proportional_r_ha"] * (1 - factor))
    assert item["custo_base"] == pytest.approx(BASE_COST)
    # the fixed share (seed, pesticides, machinery...) is untouched
    assert item["custo"] > BASE_COST - SCALE["proportional_r_ha"]


def test_margin_is_far_less_negative_than_before():
    old_margin = 140.0 * REF["prices"]["milho"]["value"] - BASE_COST
    new_margin = _item(REF, {}, _yield(140.0), "milho_1safra")["margem"]
    assert new_margin > old_margin + 1000


def test_bad_year_keeps_the_scaled_cost():
    item = _item(REF, {}, _yield(140.0, bad=100.0), "milho_1safra")
    assert item["margem_ano_ruim"] == pytest.approx(100.0 * item["preco"] - item["custo"])


def test_farmer_cost_override_is_not_scaled():
    aj = {"custo": {"milho_1safra": 7000.0}}
    item = _item(REF, aj, _yield(140.0), "milho_1safra")
    assert item["custo"] == 7000.0
    assert item["fator_escala_custo"] is None
    assert yield_cost_factor(REF, aj, "milho_1safra", 140.0) is None


def test_crops_without_a_split_are_not_scaled():
    rend = {"soja": dict(sc_ha=60.0, cv=0.1, p20_sc_ha=50.0, anos="2016-2025")}
    item = _item(REF, {}, rend, "soja")
    assert item["custo"] == pytest.approx(REF["costs"]["soja"]["coe"])
    assert item["fator_escala_custo"] is None


def test_cost_source_text_flags_the_adjustment_as_an_estimate():
    scaled = cost_source(_item(REF, {}, _yield(140.0), "milho_1safra"), "coe")
    assert "ajustados à produtividade local" in scaled and "validar" in scaled
    plain = cost_source(_item(REF, {"custo": {"milho_1safra": 7000.0}}, _yield(140.0), "milho_1safra"), "coe")
    assert "ajustados" not in plain
