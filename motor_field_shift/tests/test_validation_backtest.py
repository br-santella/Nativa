"""Tests of the backtest helpers. Run: uv run pytest tests/test_validation_backtest.py"""
import pandas as pd
import pytest

from field_shift.validation import backtest as B


def _df():
    rows = []
    for year, (corn, fallow) in zip(range(2010, 2016), [(10, -2), (-5, -2), (8, -2), (12, -2), (-20, -2), (9, -2)]):
        for opt, real, exp in (("milho_safrinha", corn, 99.0), ("pousio", fallow, -2.0)):
            rows.append(dict(cod_ibge="x", year=year, option=opt, expected=exp, realized=real))
    return pd.DataFrame(rows)


def test_track_record_uses_only_past_seasons():
    d = B.track_record(_df(), years=2).set_index(["year", "option"])["expected"]
    assert pd.isna(d[(2010, "milho_safrinha")]) and pd.isna(d[(2011, "milho_safrinha")])  # needs 2 past seasons
    assert d[(2012, "milho_safrinha")] == pytest.approx((10 - 5) / 2)
    assert d[(2015, "milho_safrinha")] == pytest.approx((12 - 20) / 2)  # 2013 and 2014, never 2015 itself


def test_strategies_pick_regret_and_oracle():
    s = B.strategies(_df())
    assert (s["engine_income_choice"] == "milho_safrinha").all()  # expected 99 always wins
    assert s.loc[s["year"] == 2014, "oracle_choice"].item() == "pousio"
    assert s["oracle"].ge(s["engine_income_pick"]).all()


@pytest.mark.skipif(not (B.RAW / "renda/conab_milho_2safra.xls").exists(), reason="CONAB sheets not downloaded")
def test_conab_cost_series_has_no_gaps_2008_2025():
    for crop in ("milho_2safra", "trigo"):
        c = B.conab_costs(crop)
        assert set(range(2008, 2026)) <= set(c.index), crop
        assert (c > 100).all()  # parsed cost values (BRL/ha), not codes or percentages
