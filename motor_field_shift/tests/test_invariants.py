"""Invariant (metamorphic) tests of the rotation engine: properties that must hold whatever the exact catalog numbers are.

See docs/validation.md, section 1. Run: uv run pytest tests/test_invariants.py
"""
from functools import lru_cache

import numpy as np
import pytest

from field_shift.app import engine as E
from field_shift.motor import recomendar
from field_shift.validation.sensitivity import Scenario, build_context, catalog_overrides, rank

CRITERIA = list(E.CRITERIOS)
SOWINGS = ["15/01", "01/02", "15/02", "01/03", "15/03"]


@lru_cache(maxsize=None)
def ctx(**kw):
    """Cached context; `irrigation` comes as a tuple of pairs so the kwargs stay hashable."""
    if "irrigation" in kw:
        kw["irrigation"] = dict(kw["irrigation"])
    return build_context(Scenario("t", "test", **kw))


def base():
    return ctx(stage="enchimento_graos")


def _corn_free(rid: str) -> bool:
    c = E.CATALOGO[E.NOME_DE[rid]]
    return not c["milho"] and c["verao"] == "soja"


def _by_id(tab):
    return tab.set_index("id")


# --------------------------------------------------------------------------- structure


def test_deterministic():
    a, b = rank(base()), rank(base())
    assert list(a["id"]) == list(b["id"]) and np.allclose(a["nota"], b["nota"])


def test_scores_and_criteria_in_unit_interval_and_sorted():
    for c in (base(), ctx(current="milho_verao__milho_safrinha", stage="grao_leitoso"), ctx(harvest="25/02")):
        tab = rank(c)
        assert tab["nota"].between(0, 1).all()
        for k in CRITERIA:
            assert tab[k].between(0, 1).all(), k
        assert tab["nota"].is_monotonic_decreasing


def test_eliminated_always_have_a_reason_and_soy_on_soy_is_out():
    res = E.pontuar(base().weights, base().rk, {}, None)
    assert res["eliminadas"] and all(m for m in res["eliminadas"].values())
    assert E.NOME_DE["soja__soja_safrinha"] in res["eliminadas"]


def test_current_rotation_always_reported():
    for cur in ("soja__milho_safrinha", "soja__pousio", "soja__soja_safrinha", "milho_verao__trigo"):
        r = recomendar({"talhao_id": "72638"}, rotacao_atual=cur, data_referencia="2026-12-01")
        assert r["atual"]["id"] == cur and r["atual"]["atual"]


# --------------------------------------------------------------------------- weights


def test_scaling_all_weights_keeps_ranking():
    w = dict(E.PESOS_PADRAO)
    a = rank(base(), weights=w)
    b = rank(base(), weights={k: 2 * v for k, v in w.items()})
    assert list(a["id"]) == list(b["id"])


@pytest.mark.parametrize("criterion", CRITERIA)
def test_more_weight_never_demotes_the_best_on_that_criterion(criterion):
    for c in (base(), ctx(harvest="25/02")):
        before = rank(c)
        best = before.sort_values(criterion, ascending=False, kind="stable")["id"].iloc[0]
        pos0 = list(before["id"]).index(best)
        for v in (5, 7, 10):
            w = dict(E.PESOS_PADRAO, **{criterion: max(v, E.PESOS_PADRAO[criterion])})
            assert list(rank(c, weights=w)["id"]).index(best) <= pos0, (criterion, v)


def test_subset_keeps_relative_order():
    """Absolute 0–1 scales: ranking a subset gives the same relative order (no min-max coupling between candidates)."""
    full = list(rank(base())["id"])
    sub = full[::2]
    res = E.pontuar(base().weights, base().rk, {}, [E.NOME_DE[i] for i in sub])
    assert [E.CATALOGO[n]["id"] for n in res["tabela"]["candidata"]] == sub


# --------------------------------------------------------------------------- income


def test_higher_corn_price_helps_corn_and_leaves_corn_free_unchanged():
    a = _by_id(rank(base()))
    b = _by_id(rank(base(), adjustments={"preco": {"milho": 80.0}}))
    for rid in a.index:
        if _corn_free(rid):
            assert b.at[rid, "renda"] == pytest.approx(a.at[rid, "renda"]), rid
        else:
            assert b.at[rid, "renda"] >= a.at[rid, "renda"] - 1e-12, rid
    # The income criterion is clipped at 1 (corn can already saturate it), so the strict check starts from a low corn price.
    low = _by_id(rank(base(), adjustments={"preco": {"milho": 30.0}}))
    assert b.at["soja__milho_safrinha", "renda"] > low.at["soja__milho_safrinha", "renda"]


@pytest.mark.parametrize("cost_key", ["milho_2safra", "trigo", "aveia", "milheto_crotalaria", "aveia_nabo", "pousio"])
def test_higher_cost_never_raises_income(cost_key):
    a = _by_id(rank(base()))
    b = _by_id(rank(base(), adjustments={"custo": {cost_key: 1e4}}))
    assert (b["renda"] <= a["renda"].reindex(b.index) + 1e-12).all()


def test_higher_bonus_never_lowers_income():
    a = _by_id(rank(base()))

    def bump(c):
        c["bonus_sc"] += 2.0

    with catalog_overrides(bump):
        b = _by_id(rank(base()))
    assert (b["renda"] >= a["renda"].reindex(b.index) - 1e-12).all()


# --------------------------------------------------------------------------- climate, water, calendar


def _crit(c, rid, k):
    return _by_id(rank(c)).at[rid, k]


@pytest.mark.parametrize("rid", ["soja__milho_safrinha", "soja__sorgo"])
def test_later_sowing_never_lowers_frost_exposure(rid):
    """Later 2nd-season sowing pushes grain filling into June–July: the climate-risk criterion must not improve."""
    risk = [_crit(ctx(sowing=s, reference_date=None), rid, "risco") for s in SOWINGS
            if rid in set(rank(ctx(sowing=s, reference_date=None))["id"])]
    assert len(risk) >= 3
    assert all(b <= a + 1e-9 for a, b in zip(risk, risk[1:])), risk


def test_irrigation_never_lowers_water_or_risk():
    dry = _by_id(rank(base()))
    wet = _by_id(rank(ctx(stage="enchimento_graos", irrigation=(("disponivel", True),))))
    for rid in dry.index:
        assert wet.at[rid, "agua"] >= dry.at[rid, "agua"] - 1e-9, rid
        assert wet.at[rid, "risco"] >= dry.at[rid, "risco"] - 1e-9, rid
    assert wet.at["soja__milho_safrinha", "agua"] > dry.at["soja__milho_safrinha", "agua"]


def test_too_late_harvest_leaves_only_fixed_date_crops():
    tab = rank(ctx(harvest="25/03"))
    assert all(not E.CATALOGO[E.NOME_DE[i]]["segue_semeadura"] for i in tab["id"])


def test_cover_crops_have_no_climate_risk():
    tab = _by_id(rank(base()))
    for rid in tab.index:
        if E.CATALOGO[E.NOME_DE[rid]]["tipo"] in ("cobertura", "pousio"):
            assert tab.at[rid, "risco"] == 1.0
