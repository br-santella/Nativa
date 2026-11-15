"""Engine precision before/after the accuracy changes (docs/validation.md, section 6).

    uv run python scripts/validation/precision.py

1. Off-season corn failure model: in-sample vs leave-one-year-out vs forward-chaining (only past seasons) evaluation of the
   engine's climate flags and of richer weather models (`field_shift.validation.failure_model`).
2. Income estimator: decision backtest of the previous engine (yield trend × last-year price − current cost) against the
   current engine (5-season track record for grain second crops), with a season-block bootstrap of the gain.
Writes CSVs to data/processed/validation/ and prints the tables used in the doc.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from field_shift.validation import backtest as B
from field_shift.validation import failure_model as F

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/processed/validation"


def failure_section() -> None:
    d = F.dataset()
    print(f"## 1. Off-season corn failures: {len(d)} municipality-years, {d['ano_pam'].nunique()} seasons "
          f"({d['ano_pam'].min()}–{d['ano_pam'].max()}), base rate {d['failure'].mean():.3f}\n")
    rows = []
    for label, pred in [("in-sample", F.in_sample_predictions(d)), ("leave-one-year-out", F.loyo_predictions(d)),
                        ("forward (past seasons only)", F.forward_predictions(d))]:
        e = F.evaluate(pred)
        e.insert(0, "evaluation", label)
        rows.append(e)
    t = pd.concat(rows, ignore_index=True)
    t.to_csv(OUT / "precision_failure_models.csv", index=False)
    print(t.drop(columns=["obs"]).to_markdown(index=False, floatfmt=".3f"))
    print("\nbetween-municipality signal (permutation within season):", F.municipal_signal(d))


def income_section(n_boot: int = 2000) -> None:
    old = B.decision_backtest(expectation="engine")
    tr = B.track_record(B.decision_backtest(), 5).rename(columns={"expected": "track"})
    d = old.merge(tr[["cod_ibge", "year", "option", "track"]], on=["cod_ibge", "year", "option"])
    # same sample for both: municipality-years where the track record exists (it needs past seasons)
    ok = d.groupby(["cod_ibge", "year"])["track"].transform(lambda s: s.notna().all())
    d = d[ok].reset_index(drop=True)
    new = d.assign(expected=d["track"])
    s_old, s_new = B.strategies(d), B.strategies(new)
    rows = []
    for label, s, x in [("previous engine (trend yield × last-year price − cost)", s_old, d),
                        ("current engine (5-season track record)", s_new, new)]:
        rows.append(dict(estimator=label, n=len(s), pick=s["engine_income_pick"].mean(), always_corn=s["always_milho_safrinha"].mean(),
                         oracle=s["oracle"].mean(), regret=(s["oracle"] - s["engine_income_pick"]).mean(),
                         hit_rate=(s["engine_income_choice"] == s["oracle_choice"]).mean(),
                         picks_fallow=(s["engine_income_choice"] == "pousio").mean(),
                         margin_mae=(x["expected"] - x["realized"]).abs().mean()))
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "precision_income.csv", index=False)
    print("\n## 2. Income estimator, decision backtest (soybean bags/ha/yr, no bonus)\n")
    print(t.to_markdown(index=False, floatfmt=".2f"))
    gain = (s_new.set_index(["cod_ibge", "year"])["engine_income_pick"] - s_old.set_index(["cod_ibge", "year"])["engine_income_pick"])
    by = gain.groupby(level=1).mean()
    rng = np.random.default_rng(0)
    bs = [by.loc[rng.choice(by.index.values, len(by))].mean() for _ in range(n_boot)]
    print(f"\ngain {by.mean():+.2f} bags/ha/yr; better in {(by > 0).sum()} of {len(by)} seasons (ties {(by == 0).sum()}); "
          f"90 % season-bootstrap interval {np.quantile(bs, 0.05):+.2f} to {np.quantile(bs, 0.95):+.2f}")
    mae = d.assign(engine=(d["expected"] - d["realized"]).abs(), track_err=(d["track"] - d["realized"]).abs())
    print("\nmargin MAE by option (bags/ha):")
    print(mae.groupby("option")[["engine", "track_err"]].mean().round(2).to_markdown())
    by.rename("gain").to_csv(OUT / "precision_income_by_season.csv")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    failure_section()
    income_section()
