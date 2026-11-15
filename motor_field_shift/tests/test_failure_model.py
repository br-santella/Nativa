"""Out-of-sample evaluation of the off-season corn failure model (field_shift.validation.failure_model). Synthetic data only."""
import numpy as np
import pandas as pd

from field_shift.validation import failure_model as F

MODELS = {"base_rate": [], "x": ["x"]}


def _data(seed=0, years=12, muns=8):
    rng = np.random.default_rng(seed)
    rows = [dict(cod_ibge=str(m), ano_pam=2000 + y, x=rng.normal()) for y in range(years) for m in range(muns)]
    d = pd.DataFrame(rows)
    d["failure"] = rng.random(len(d)) < 1 / (1 + np.exp(-(d["x"] * 2 - 1)))
    return d


def test_leave_one_year_out_never_sees_the_test_season():
    d = _data()
    a = F.loyo_predictions(d, MODELS)
    flipped = d.copy()
    held = flipped["ano_pam"] == 2005
    flipped.loc[held, "failure"] = ~flipped.loc[held, "failure"]
    b = F.loyo_predictions(flipped, MODELS)
    assert np.allclose(a.loc[held, "x"], b.loc[held, "x"]) and np.allclose(a.loc[held, "base_rate"], b.loc[held, "base_rate"])


def test_forward_uses_only_past_seasons():
    d = _data()
    a = F.forward_predictions(d, MODELS, min_train_years=5)
    later = d.copy()
    later.loc[later["ano_pam"] == 2011, "failure"] = True        # change the last season only
    b = F.forward_predictions(later, MODELS, min_train_years=5)
    early = a["ano_pam"] < 2011
    assert a["ano_pam"].min() == 2005 and np.allclose(a.loc[early, "x"], b.loc[early, "x"])


def test_informative_feature_beats_base_rate_out_of_sample():
    e = F.evaluate(F.loyo_predictions(_data(years=20, muns=30), MODELS), n_boot=200).set_index("model")
    assert e.at["x", "bss"] > 0.05 and e.at["base_rate", "bss"] == 0
