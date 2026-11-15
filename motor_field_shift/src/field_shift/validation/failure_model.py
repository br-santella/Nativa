"""Off-season corn failure model, validated out of sample (docs/validation.md, section 6).

Question: can the daily NASA POWER weather of each season predict which municipality-years of off-season corn fail in IBGE
PAM (yield ≥ 15 % below the municipal trend) better than the engine's current frost/deficit flags?

Overfitting guard. Failures are driven by the season (the whole Oeste fails together), so the 1,143 municipality-years hold
only ~23 independent seasons. Every model is therefore evaluated with **leave-one-year-out** cross-validation (the season being
predicted is never seen in training, neither by the coefficients nor by the regularization), the candidate models are a short
list fixed in advance from agronomy (not searched over the data), and the gain over the base rate carries a season-block
bootstrap interval. A model only replaces the engine flags if its out-of-sample gain is positive with that interval above zero.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
POWER = ROOT / "data/processed/clima_pr/power_diario.parquet"
SOWING = (2, 15)        # 15/02: typical Oeste off-season corn sowing, same as the backtest flags

# Windows in days after sowing (off-season corn, ~120–150 day cycle; flowering ~60–70 days after sowing).
FROST_WINDOW = (60, 120)     # same window as the engine's frost indicator
FLOWERING_WINDOW = (50, 85)
HARVEST_WINDOW = (120, 160)
ESTABLISHMENT_WINDOW = (0, 60)
FROST_T = 3.0                # °C, engine threshold (POWER underestimates frost against INMET)
HEAT_T = 32.0                # °C, Tmax above which corn pollination suffers

# Candidate models, fixed a priori (agronomic reasoning, not data search). Each adds one block to the previous one.
MODELS: dict[str, list[str]] = {
    "base_rate": [],
    "engine_flags": ["frost_flag", "deficit_flag"],
    "frost_deficit_continuous": ["frost_dd", "deficit_gap"],
    "+heat_harvest_rain": ["frost_dd", "deficit_gap", "heat_days", "rain_harvest"],
    "+establishment_temp": ["frost_dd", "deficit_gap", "heat_days", "rain_harvest", "tmean_establishment"],
}


def _window(g: pd.DataFrame, sow: pd.Timestamp, w: tuple[int, int]) -> pd.DataFrame:
    return g.loc[sow + pd.Timedelta(days=w[0]): sow + pd.Timedelta(days=w[1])]


def season_features(g: pd.DataFrame, year: int, sowing: tuple[int, int] = SOWING) -> dict:
    """Weather features of the off-season corn sown on `sowing` of `year` (calendar year of sowing and harvest), from one
    point's daily POWER table indexed by date."""
    sow = pd.Timestamp(year, *sowing)
    fr = _window(g, sow, FROST_WINDOW)["T2M_MIN"]
    fl = _window(g, sow, FLOWERING_WINDOW)["T2M_MAX"]
    hv = _window(g, sow, HARVEST_WINDOW)["PRECTOTCORR"]
    es = _window(g, sow, ESTABLISHMENT_WINDOW)["T2M"]
    if fr.notna().sum() < 40 or hv.notna().sum() < 30:
        return {}
    return dict(frost_flag=float((fr <= FROST_T).any()), frost_dd=float((FROST_T - fr).clip(lower=0).sum()),
                heat_days=float((fl >= HEAT_T).sum()), rain_harvest=float(hv.sum()), tmean_establishment=float(es.mean()))


@lru_cache(maxsize=1)
def municipal_features() -> pd.DataFrame:
    """Season features at every Oeste municipality centroid (POWER `mun_` points), PAM years 2003–2025."""
    cols = ["data", "ponto_id", "T2M", "T2M_MIN", "T2M_MAX", "PRECTOTCORR"]
    d = pd.read_parquet(POWER, columns=cols, filters=[("tipo", "==", "municipio")])
    rows = []
    for pid, g in d.groupby("ponto_id"):
        g = g.set_index("data").sort_index()
        for year in range(2003, 2026):
            f = season_features(g, year)
            if f:
                rows.append(dict(cod_ibge=pid[4:], ano_pam=year, **f))
    return pd.DataFrame(rows)



def dataset() -> pd.DataFrame:
    """PAM failures (backtest definition) joined with the season features and the engine's deficit ratio (FAO-56 balance)."""
    from field_shift.water.balance import DEFICIT_THRESHOLD
    from field_shift.validation.backtest import corn_failures
    d = corn_failures().dropna(subset=["ratio"]).drop(columns=["frost"])
    d = d.merge(municipal_features(), on=["cod_ibge", "ano_pam"], how="inner")
    d["deficit_flag"] = (d["ratio"] < DEFICIT_THRESHOLD).astype(float)
    d["deficit_gap"] = (1.0 - d["ratio"]).clip(lower=0)      # share of the crop water demand not met in the critical phase
    return d.reset_index(drop=True)


# Models


def _fit_predict(train: pd.DataFrame, test: pd.DataFrame, feats: list[str]) -> np.ndarray:
    """Logistic regression (L2, standardized inputs, fixed C = 1) or the training base rate when there are no features. The
    two flag models are fitted the same way (equivalent to the empirical failure rate of each flag combination)."""
    if not feats:
        return np.full(len(test), train["failure"].mean())
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    m.fit(train[feats].values, train["failure"].values)
    return m.predict_proba(test[feats].values)[:, 1]


def loyo_predictions(d: pd.DataFrame, models: dict[str, list[str]] = MODELS) -> pd.DataFrame:
    """Leave-one-year-out out-of-sample failure probability of each model for every municipality-year."""
    out = d[["cod_ibge", "ano_pam", "failure"]].copy()
    for name, feats in models.items():
        p = np.empty(len(d))
        for year in d["ano_pam"].unique():
            te = (d["ano_pam"] == year).values
            p[te] = _fit_predict(d[~te], d[te], feats)
        out[name] = p
    return out


def forward_predictions(d: pd.DataFrame, models: dict[str, list[str]] = MODELS, min_train_years: int = 10) -> pd.DataFrame:
    """Expanding-window (forward-chaining) predictions: season Y is predicted by a model trained only on seasons before Y, as
    the engine would be used. Seasons with fewer than `min_train_years` past seasons are skipped."""
    years = sorted(d["ano_pam"].unique())
    test_years = years[min_train_years:]
    sub = d[d["ano_pam"].isin(test_years)]
    out = sub[["cod_ibge", "ano_pam", "failure"]].copy()
    for name, feats in models.items():
        p = pd.Series(np.nan, index=sub.index)
        for year in test_years:
            te = sub["ano_pam"] == year
            p[te] = _fit_predict(d[d["ano_pam"] < year], sub[te], feats)
        out[name] = p.values
    return out


def in_sample_predictions(d: pd.DataFrame, models: dict[str, list[str]] = MODELS) -> pd.DataFrame:
    """Fitted on all seasons and scored on the same seasons (optimistic; shown only to measure the overfitting gap)."""
    out = d[["cod_ibge", "ano_pam", "failure"]].copy()
    for name, feats in models.items():
        out[name] = _fit_predict(d, d, feats)
    return out


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else np.nan


def evaluate(pred: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Out-of-sample metrics per model: Brier, Brier skill score vs the base rate (with a 90 % season-block bootstrap interval),
    AUC, mean probability vs observed rate, and the Spearman correlation between municipalities (mean predicted vs observed)."""
    y = pred["failure"].astype(float).values
    years = pred["ano_pam"].values
    uniq = np.unique(years)
    idx = {yr: np.flatnonzero(years == yr) for yr in uniq}
    rng = np.random.default_rng(seed)
    boots = [np.concatenate([idx[yr] for yr in rng.choice(uniq, len(uniq))]) for _ in range(n_boot)]
    base = pred["base_rate"].values
    rows = []
    for name in [c for c in pred.columns if c not in ("cod_ibge", "ano_pam", "failure")]:
        p = pred[name].values
        bss = 1 - _brier(y, p) / _brier(y, base)
        bs = np.array([1 - _brier(y[b], p[b]) / _brier(y[b], base[b]) for b in boots])
        mun = pred.assign(p=p).groupby("cod_ibge").agg(p=("p", "mean"), obs=("failure", "mean"))
        yr = pred.assign(p=p).groupby("ano_pam").agg(p=("p", "mean"), obs=("failure", "mean"))
        # within-season AUC: ranks municipalities inside the same season (the pooled AUC mixes in the season-level shift of the
        # base rate, which leave-one-year-out biases downward)
        w = [(_auc(g["failure"].values.astype(float), g["p"].values), len(g)) for _, g in pred.assign(p=p).groupby("ano_pam")]
        w = [(a, n) for a, n in w if not np.isnan(a)]
        rows.append(dict(model=name, brier=_brier(y, p), bss=bss, bss_lo=float(np.quantile(bs, 0.05)),
                         bss_hi=float(np.quantile(bs, 0.95)), auc_within_season=float(np.average([a for a, _ in w], weights=[n for _, n in w])) if w else np.nan,
                         spearman_season=float(yr["p"].corr(yr["obs"], method="spearman")), mean_p=float(p.mean()),
                         obs=float(y.mean()), spearman_mun=float(mun["p"].corr(mun["obs"], method="spearman"))))
    return pd.DataFrame(rows)


def municipal_signal(d: pd.DataFrame, n_perm: int = 2000, seed: int = 0) -> dict:
    """Is there any between-municipality difference in failure frequency beyond chance, once the season is accounted for?
    Permutes the failure flags among municipalities within each season (keeps every season's failure share) and compares the
    spread of the municipal failure rates with the observed one."""
    rng = np.random.default_rng(seed)
    obs = d.groupby("cod_ibge")["failure"].mean().std()
    groups = [g.index.values for _, g in d.groupby("ano_pam")]
    f = d["failure"].values.astype(float)
    sims = []
    for _ in range(n_perm):
        g = f.copy()
        for ix in groups:
            g[ix] = rng.permutation(f[ix])
        sims.append(pd.Series(g, index=d.index).groupby(d["cod_ibge"]).mean().std())
    sims = np.array(sims)
    return dict(sd_observed=float(obs), sd_chance_median=float(np.median(sims)), p_value=float((sims >= obs).mean()))
