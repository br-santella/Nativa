"""Historical backtest of the engine against what actually happened (docs/validation.md, section 3).

Three checks, using only information available before each season. Scope (`set_scope`): "oeste" (default: the 50 municipalities
of the Oeste mesoregion, the pilot the engine was tuned on) or "pr" (all 399 municipalities of
Paraná; `mesoregions()` maps each one to its IBGE mesoregion; used by scripts/validation/statewide.py, section 7):

a) Yield expectation: the engine uses the mean of the last 10 years of IBGE PAM (and p20 as the "bad year"). Does that mean
   predict the next year, and does the realized yield fall below p20 in ~20 % of the years?
b) Climate risk: does the engine's loss probability for off-season corn (frost + water deficit; before: frost + dry spell) match how often PAM
   shows a real crop failure (yield ≥ 15 % below the municipal trend)?
c) Decision: each year, pick the second crop with the engine's income logic (expected margin with the information of the
   previous year) and compare the realized margin with fixed strategies and with the ex-post best option.

Money is expressed in **bags of soybean per hectare** (BRL ÷ soybean price of the same year), so years can be averaged
without a deflator. Prices are realized prices from PAM (production value ÷ production, per municipality and year);
costs are the CONAB variable cost (COE) sheets for Paraná of each season.
"""
from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from field_shift.app import engine as E
from field_shift.pam.productivity import expected_yield
from field_shift.income.history import _conab_line, conab_costs  # noqa: F401 (re-exported for the tests)

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw"
WINDOW = 10            # years of PAM history the engine averages
FAIL_DEV = -0.15       # crop failure: yield 15 % or more below the municipal linear trend
FIRST_YEAR, LAST_YEAR = 2008, 2025
KG_PER_BAG = 60.0
SCOPES = ("oeste", "pr")
_SCOPE = "oeste"


def set_scope(scope: str) -> None:
    """Switch the backtest between the Oeste pilot ("oeste") and all of Paraná ("pr"); clears the cached tables."""
    global _SCOPE
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}")
    _SCOPE = scope
    pam.cache_clear()


def scope() -> str:
    return _SCOPE


def mesoregions() -> pd.Series:
    """cod_ibge -> short IBGE mesoregion label ('Oeste do PR', 'Norte Central do PR'...), for the 399 municipalities."""
    from field_shift.income.income import MESOREGIONS, region_label
    m = pd.read_csv(MESOREGIONS, dtype={"cod_ibge": str})
    return m.set_index("cod_ibge")["mesorregiao"].map(region_label)


# Data


@lru_cache(maxsize=1)
def pam() -> pd.DataFrame:
    """Long PAM table of the scope (cod_ibge, ano, cultura, variavel, valor), main + extra crops."""
    files = (("pam_oeste_pr", "pam_extra_oeste_pr") if _SCOPE == "oeste" else ("pam_pr", "pam_extra_pr"))
    p = pd.concat([pd.read_parquet(RAW / f"ibge/{f}.parquet") for f in files])
    p["cod_ibge"] = p["cod_ibge"].astype(str)
    p = p.dropna(subset=["valor"])
    p["ano"] = p["ano"].astype(int)
    return p


def yields(crop: str) -> pd.DataFrame:
    """Yield in bags/ha, columns = municipalities, index = year."""
    p = pam()
    y = p[(p["cultura"] == crop) & (p["variavel"] == "rendimento_kg_ha")]
    return y.pivot_table(index="ano", columns="cod_ibge", values="valor") / KG_PER_BAG


def prices(crop: str) -> pd.Series:
    """Realized price (BRL per 60 kg bag) per year, aggregate of the scope (Oeste or Paraná): Σ production value / Σ production
    (PAM table 1612)."""
    p = pam()
    p = p[p["cultura"] == crop]
    v = p[p["variavel"] == "valor_mil_reais"].groupby("ano")["valor"].sum() * 1000
    q = p[p["variavel"] == "producao_t"].groupby("ano")["valor"].sum() * 1000 / KG_PER_BAG
    both = pd.concat([v, q], axis=1, keys=["v", "q"]).dropna()
    return (both["v"] / both["q"]).rename(crop)


@lru_cache(maxsize=1)
def climate_flags(sowing: str = "15/02") -> pd.DataFrame:
    """Per municipality and PAM year: frost (Tmin ≤ 3 °C) in the critical phase of off-season corn sown on `sowing` and dry spell
    ≥ 15 days in Mar–Apr (NASA POWER at the municipality centroid). Agricultural year Y → off-season corn harvested in Y + 1."""
    a = pd.read_parquet(ROOT / "data/processed/clima_pr/indicadores_anuais.parquet", columns=["ponto_id", "ano", "indicador", "valor"])
    ind = {f"geada_safrinha_semeadura_{sowing.replace('/', '')}_le3": "frost", "veranico_safrinha_ge15": "dry_spell"}
    a = a[a["ponto_id"].str.startswith("mun_") & a["indicador"].isin(ind)]
    a = a.pivot_table(index=["ponto_id", "ano"], columns="indicador", values="valor").rename(columns=ind).reset_index()
    a["cod_ibge"] = a["ponto_id"].str[4:]
    a["ano_pam"] = a["ano"] + 1
    return a[["cod_ibge", "ano_pam", "frost", "dry_spell"]]


DEFICIT_FILE = ROOT / "data/processed/validation/backtest_deficit_flags.parquet"
DEFICIT_FILE_PR = ROOT / "data/processed/validation/backtest_deficit_flags_pr.parquet"


def deficit_flags(sowing: str = "15/02") -> pd.DataFrame:
    """Per municipality of the scope and PAM year: ETa/ETc of off-season corn in the critical phase (FAO-56 daily balance, NASA
    POWER + SoilGrids soil at the centroid, same path as a field) and the engine's deficit flag (ratio < DEFICIT_THRESHOLD).
    Cached in data/processed/validation/ (the balance takes ~1 min for the Oeste, ~8 min for Paraná)."""
    from field_shift.water.balance import DEFICIT_THRESHOLD, YEARS, critical_phase_water
    from field_shift.validation import zarc as Z
    f = DEFICIT_FILE if _SCOPE == "oeste" else DEFICIT_FILE_PR
    if sowing != "15/02":  # the default keeps the original cache names
        f = f.with_name(f"{f.stem}_{sowing.replace('/', '')}{f.suffix}")
    if f.exists():
        d = pd.read_parquet(f)
    else:
        rows = []
        mun = Z.municipalities()
        for m in (mun.query("oeste") if _SCOPE == "oeste" else mun).itertuples():
            rk = Z.engine_side(m.lat_c, m.lon_c, sowing)
            ac = (rk or {}).get("agua_ctx")
            if ac is None:
                continue
            b = critical_phase_water("milho_safrinha", ac["ponto_id"], sowing, ac["cad_camadas"])
            rows += [dict(cod_ibge=str(m.geocodigo), ano_pam=y + 1, ratio=float(r)) for y, r in zip(YEARS, b["razoes"])]
        d = pd.DataFrame(rows)
        f.parent.mkdir(parents=True, exist_ok=True)
        d.to_parquet(f)
    d["deficit"] = (d["ratio"] < DEFICIT_THRESHOLD).astype(float)
    return d


# A) yield expectation


def yield_expectation(crop: str) -> pd.DataFrame:
    """Rolling 10-year mean and p20 (years Y−10..Y−1) against the realized yield of Y, per municipality and year."""
    y = yields(crop)
    rows = []
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        hist = y.loc[(y.index >= year - WINDOW) & (y.index < year)]
        if year not in y.index or len(hist) < 5:
            continue
        for cod in y.columns:
            h = hist[cod].dropna()
            real = y.at[year, cod]
            if len(h) < 5 or pd.isna(real):
                continue
            rows.append(dict(crop=crop, cod_ibge=cod, year=year, expected=h.mean(), p20=h.quantile(0.2), realized=real,
                             trend=np.polyval(np.polyfit(h.index, h.values, 1), year), engine=expected_yield(h)[0]))
    return pd.DataFrame(rows)


def yield_metrics(df: pd.DataFrame) -> dict:
    err = (df["expected"] - df["realized"]) / df["realized"]
    terr = (df["trend"] - df["realized"]) / df["realized"]
    eerr = (df["engine"] - df["realized"]) / df["realized"]
    return dict(n=len(df), mape_mean=float(err.abs().median()), bias_mean=float(err.median()),
                mape_trend=float(terr.abs().median()), bias_trend=float(terr.median()),
                mape_engine=float(eerr.abs().median()), bias_engine=float(eerr.median()),
                below_p20=float((df["realized"] < df["p20"]).mean()),
                below_p20_capped=float((df["realized"] < np.minimum(df["p20"], df["engine"])).mean()))


# B) climate risk vs realized failures


def corn_failures(sowing: str = "15/02") -> pd.DataFrame:
    """Off-season corn: yield deviation from the municipal linear trend (fitted on 2003–2025) and crop-failure flag, with the
    frost and water-deficit flags of off-season corn sown on `sowing`."""
    y = yields("milho_2safra")
    rows = []
    for cod in y.columns:
        s = y[cod].dropna()
        if len(s) < 10:
            continue
        trend = np.polyval(np.polyfit(s.index, s.values, 1), s.index)
        for year, v, t in zip(s.index, s.values, trend):
            rows.append(dict(cod_ibge=cod, ano_pam=int(year), dev=(v - t) / t))
    d = pd.DataFrame(rows)
    d["failure"] = d["dev"] <= FAIL_DEV
    d = d.merge(climate_flags(sowing), on=["cod_ibge", "ano_pam"], how="inner")
    return d.merge(deficit_flags(sowing)[["cod_ibge", "ano_pam", "ratio", "deficit"]], on=["cod_ibge", "ano_pam"], how="left")


def risk_vs_failures() -> dict:
    """Event level (does a frost/dry-spell year coincide with a failure?) and municipality level (engine loss probability vs
    observed failure frequency)."""
    d = corn_failures().dropna(subset=["deficit"])
    d["event"] = (d["frost"] > 0) | (d["dry_spell"] > 0)
    d["event_new"] = (d["frost"] > 0) | (d["deficit"] > 0)
    out = dict(n=len(d), years=f"{d['ano_pam'].min()}–{d['ano_pam'].max()}", base_failure=float(d["failure"].mean()))
    for k in ("frost", "dry_spell", "deficit", "event", "event_new"):
        flag = d[k] > 0
        out[k] = dict(share_years=float(flag.mean()), failure_if_flag=float(d.loc[flag, "failure"].mean()),
                      failure_if_not=float(d.loc[~flag, "failure"].mean()),
                      mean_dev_if_flag=float(d.loc[flag, "dev"].mean()), mean_dev_if_not=float(d.loc[~flag, "dev"].mean()),
                      recall=float(flag[d["failure"]].mean()))
    # engine loss probability = 1 − (1 − P(frost))(1 − P(dry spell)), climatology of the same years
    m = d.groupby("cod_ibge").agg(p_frost=("frost", "mean"), p_dry=("dry_spell", "mean"), p_deficit=("deficit", "mean"),
                                  obs_failure=("failure", "mean"))
    m["engine_loss_old"] = 1 - (1 - m["p_frost"]) * (1 - m["p_dry"])
    m["engine_loss"] = 1 - (1 - m["p_frost"]) * (1 - m["p_deficit"])
    out["municipal"] = dict(mean_engine_loss_old=float(m["engine_loss_old"].mean()), mean_engine_loss=float(m["engine_loss"].mean()),
                            mean_obs_failure=float(m["obs_failure"].mean()),
                            spearman_old=float(m["engine_loss_old"].corr(m["obs_failure"], method="spearman")),
                            spearman=float(m["engine_loss"].corr(m["obs_failure"], method="spearman")))
    # by year (regional): share of municipalities with failure vs with frost
    yr = d.groupby("ano_pam").agg(failure=("failure", "mean"), frost=("frost", "mean"), dry=("dry_spell", "mean"),
                                  deficit=("deficit", "mean"), dev=("dev", "mean"))
    out["by_year"] = yr
    out["municipal_table"] = m
    return out


# C) decision backtest


OPTIONS = ("milho_safrinha", "milho_braquiaria", "trigo", "aveia", "milheto_crotalaria", "pousio")
GRAIN = {"milho_safrinha": ("milho_2safra", "milho_total", "milho_2safra"),   # PAM yield, PAM price, CONAB cost
         "milho_braquiaria": ("milho_2safra", "milho_total", "milho_2safra"),
         "trigo": ("trigo", "trigo", "trigo")}


def _cover_cost_bags() -> dict:
    """Establishment cost of covers/fallow in soybean bags (current reference cost ÷ current soybean price), kept constant in
    bags across years (no historical series exists)."""
    from field_shift.income.income import load_reference
    ref = load_reference()
    soy = ref["prices"]["soja"]["value"]
    return {k: ref["costs"][k]["coe"] / soy for k in ("aveia", "milheto_crotalaria", "pousio", "braquiaria_consorcio")}


def decision_backtest(with_bonus: bool = False, expectation: str = "mean", price_years: int = 1) -> pd.DataFrame:
    """One row per municipality × year × option: expected margin (information up to the previous year) and realized margin,
    both in soybean bags/ha. Bonus on the following soybean (catalog estimate) is added to both only if `with_bonus`.
    `expectation`: "mean" = 10-year PAM mean (the engine before the backtest); "trend" = linear trend of the same 10 years at
    year Y; "engine" = the engine's current estimator (`pam.produtividade.expected_yield`: trend clipped to the window min–max).
    `price_years`: expected price ratio (crop / soybean) = mean of the last N years (1 = last year only, like a price snapshot);
    costs are converted with last year's soybean price in both cases."""
    soy_p = prices("soja")
    covers = _cover_cost_bags()
    ys = {k: yields(v[0]) for k, v in GRAIN.items()}
    ps = {k: prices(v[1]) for k, v in GRAIN.items()}
    cs = {k: conab_costs(v[2]) for k, v in GRAIN.items()}
    rows = []
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        if year not in soy_p.index or year - 1 not in soy_p.index:
            continue
        for cod in ys["milho_safrinha"].columns:
            for opt in OPTIONS:
                bonus = E.SECOND[opt]["bonus_sc"] if with_bonus else 0.0
                if opt in GRAIN:
                    y = ys[opt]
                    hist = y.loc[(y.index >= year - WINDOW) & (y.index < year), cod].dropna() if cod in y.columns else pd.Series()
                    real_y = y.at[year, cod] if cod in y.columns and year in y.index else np.nan
                    cost = cs[opt].get(year, np.nan)
                    if len(hist) < 5 or pd.isna(real_y) or pd.isna(cost) or year not in ps[opt] or year - 1 not in ps[opt]:
                        continue
                    extra = covers["braquiaria_consorcio"] if opt == "milho_braquiaria" else 0.0
                    # decision uses last year's price ratio and this season's CONAB (ex-ante) cost
                    y_exp = (hist.mean() if expectation == "mean" else expected_yield(hist)[0] if expectation == "engine"
                             else float(np.polyval(np.polyfit(hist.index, hist.values, 1), year)))
                    past = [t for t in range(year - price_years, year) if t in ps[opt].index and t in soy_p.index]
                    ratio = float(np.mean([ps[opt][t] / soy_p[t] for t in past]))
                    exp = y_exp * ratio - cost / soy_p[year - 1] - extra + bonus
                    real = real_y * ps[opt][year] / soy_p[year] - cost / soy_p[year] - extra + bonus
                else:
                    exp = real = -covers[opt] + bonus
                rows.append(dict(cod_ibge=cod, year=year, option=opt, expected=exp, realized=real))
    return pd.DataFrame(rows)


def track_record(df: pd.DataFrame, years: int = 5) -> pd.DataFrame:
    """Replace `expected` with the mean realized margin of the option in the previous `years` seasons of the municipality
    (a track-record estimator: it carries the price, yield and cost risk the snapshot misses)."""
    r = df.pivot_table(index=["cod_ibge", "year"], columns="option", values="realized")
    e = r.groupby(level=0).transform(lambda s: s.shift(1).rolling(years, min_periods=2).mean())
    return df.drop(columns="expected").merge(e.stack().rename("expected").reset_index(), on=["cod_ibge", "year", "option"])


def strategies(df: pd.DataFrame) -> pd.DataFrame:
    """Realized margin of each strategy per municipality-year (only municipality-years where every option is available)."""
    wide_e = df.pivot_table(index=["cod_ibge", "year"], columns="option", values="expected")
    wide_r = df.pivot_table(index=["cod_ibge", "year"], columns="option", values="realized")
    ok = wide_r.dropna().index.intersection(wide_e.dropna().index)
    wide_e, wide_r = wide_e.loc[ok], wide_r.loc[ok]
    out = pd.DataFrame(index=ok)
    for opt in wide_r.columns:
        out[f"always_{opt}"] = wide_r[opt]
    pick = wide_e.idxmax(axis=1)
    out["engine_income_pick"] = [wide_r.at[i, p] for i, p in pick.items()]
    out["engine_income_choice"] = pick
    out["oracle"] = wide_r.max(axis=1)
    out["oracle_choice"] = wide_r.idxmax(axis=1)
    return out.reset_index()
