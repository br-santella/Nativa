"""Tests of the satellite helpers with synthetic NDVI series (no download). Run: uv run pytest tests/test_validation_satellite.py"""
import numpy as np
import pandas as pd

from field_shift.validation import satellite as S


def _curve(days: pd.DatetimeIndex, double: bool) -> np.ndarray:
    """Soybean peak in early January; second crop peak in late April only if `double`; bare soil (0.2) otherwise."""
    doy = np.array([(d - pd.Timestamp(d.year if d.month >= 9 else d.year - 1, 9, 1)).days for d in days])
    soy = 0.7 * np.exp(-((doy - 125) / 30.0) ** 2)
    second = 0.6 * np.exp(-((doy - 235) / 30.0) ** 2) if double else 0.0
    return 0.2 + soy + second


def _obs(fid: str, pattern: list[bool]) -> pd.DataFrame:
    days = pd.date_range("2019-07-01", f"{2019 + len(pattern)}-09-30", freq="5D")
    y0 = np.array([d.year if d.month >= 9 else d.year - 1 for d in days])
    vals = np.concatenate([_curve(days[y0 == y], pattern[min(max(y - 2019, 0), len(pattern) - 1)]) for y in sorted(set(y0))])
    return pd.DataFrame(dict(id=fid, data=days, sensor="S30", ndvi_mean=vals, frac_clear=1.0))


def test_field_years_detects_double_and_single_crop_and_bare_days():
    ndvi = pd.concat([_obs("a", [True, True, True]), _obs("b", [False, False, False])])
    fy = S.field_years(ndvi)
    a, b = fy[fy["id"] == "a"], fy[fy["id"] == "b"]
    assert len(a) == 3 and a["double"].all()
    assert len(b) == 3 and not b["double"].any()
    assert (b["bare_days"].values > a["bare_days"].values + 60).all()


def test_gappy_years_are_dropped():
    o = _obs("a", [True, True, True])
    o = o[~o["data"].between("2020-12-01", "2021-03-15")]  # 3.5 months without a clear observation
    fy = S.field_years(o)
    assert "2020/21" not in set(fy["year"])


def test_following_soy_effect_shape():
    ndvi = pd.concat([_obs("a", [True, False, True]), _obs("b", [False, True, False])])
    eff = S.following_soy_effect(S.field_years(ndvi))
    assert set(eff["outcome"]) == {"summer_peak of next summer", "summer_integral of next summer"}
    assert (eff["n"] > 0).all()
