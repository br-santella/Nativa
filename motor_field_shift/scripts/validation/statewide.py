"""Statewide validation: the Oeste checks repeated for all of Paraná, reported by IBGE mesoregion (docs/validation.md, section 7).

    uv run python scripts/validation/statewide.py            # all sections
    uv run python scripts/validation/statewide.py income     # one section: income | covers | risk | engine

1. income  — decision backtest of the income estimator (previous engine: trend yield × last-year price − cost; current engine:
             5-season track record), per mesoregion, with a season-block bootstrap of the gain for Paraná.
2. covers  — is "cover crop first" outside the Oeste supported by what happened? Realized margin of always-corn vs the cover
             (millet/crotalaria, cost only) per mesoregion, with and without the catalog bonus on the next soybean.
3. risk    — off-season corn climate risk (frost + water deficit, the engine's criterion) vs PAM failures, per mesoregion, at
             the engine's default sowing (01/02) and at 15/02.
4. engine  — what the full engine (all criteria, default weights) ranks first at each municipality centroid, per mesoregion.
Writes CSVs to data/processed/validation/statewide_*.csv and prints the tables used in the doc.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from field_shift.validation import backtest as B

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/processed/validation"
COVERS = ("milheto_crotalaria", "aveia", "pousio")


def _with_meso(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(meso=df["cod_ibge"].astype(str).map(B.mesoregions()))


def _boot(by_season: pd.Series, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    bs = [by_season.loc[rng.choice(by_season.index.values, len(by_season))].mean() for _ in range(n)]
    return float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95))


def income_section() -> pd.DataFrame:
    old = B.decision_backtest(expectation="engine")
    tr = B.track_record(B.decision_backtest(), 5).rename(columns={"expected": "track"})
    d = old.merge(tr[["cod_ibge", "year", "option", "track"]], on=["cod_ibge", "year", "option"])
    ok = d.groupby(["cod_ibge", "year"])["track"].transform(lambda s: s.notna().all())
    d = d[ok].reset_index(drop=True)
    s_old = _with_meso(B.strategies(d))
    s_new = _with_meso(B.strategies(d.assign(expected=d["track"])))
    rows = []
    for meso, g_new in [("Paraná", s_new), *s_new.groupby("meso")]:
        g_old = s_old if meso == "Paraná" else s_old[s_old["meso"] == meso]
        gain = (g_new.set_index(["cod_ibge", "year"])["engine_income_pick"]
                - g_old.set_index(["cod_ibge", "year"])["engine_income_pick"]).groupby(level=1).mean()
        lo, hi = _boot(gain)
        rows.append(dict(mesorregiao=meso, municipios=g_new["cod_ibge"].nunique(), n=len(g_new),
                         previous=g_old["engine_income_pick"].mean(), current=g_new["engine_income_pick"].mean(),
                         always_corn=g_new["always_milho_safrinha"].mean(), oracle=g_new["oracle"].mean(),
                         gain=gain.mean(), gain_p05=lo, gain_p95=hi, seasons_better=f"{(gain > 0).sum()}/{len(gain)}",
                         hit_rate=(g_new["engine_income_choice"] == g_new["oracle_choice"]).mean(),
                         picks_cover=g_new["engine_income_choice"].isin(COVERS).mean()))
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "statewide_income.csv", index=False)
    print("\n## 1. Income estimator, decision backtest by mesoregion (soybean bags/ha/yr, no bonus)\n")
    print(t.to_markdown(index=False, floatfmt=".2f"))
    return t


def covers_section() -> pd.DataFrame:
    rows = []
    for bonus in (False, True):
        s = _with_meso(B.strategies(B.decision_backtest(with_bonus=bonus)))
        for meso, g in [("Paraná", s), *s.groupby("meso")]:
            corn, cover = g["always_milho_safrinha"], g["always_milheto_crotalaria"]
            rows.append(dict(mesorregiao=meso, bonus=bonus, n=len(g), corn=corn.mean(), cover=cover.mean(),
                             corn_minus_cover=(corn - cover).mean(), cover_beats_corn=(cover > corn).mean(),
                             oracle_is_cover=g["oracle_choice"].isin(COVERS).mean()))
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "statewide_covers.csv", index=False)
    print("\n## 2. Cover crop vs off-season corn, realized (soybean bags/ha/yr)\n")
    print(t.to_markdown(index=False, floatfmt=".2f"))
    return t


def risk_section() -> pd.DataFrame:
    """At the engine's default sowing (01/02) and at 15/02 (the Oeste backtest date, §3.4): the calibration depends on the date,
    which the PAM does not record."""
    from field_shift.crop_calendar import DEFAULT_SOWING
    rows = []
    for sowing in (DEFAULT_SOWING, "15/02"):
        d = _with_meso(B.corn_failures(sowing).dropna(subset=["deficit"]))
        for meso, g in [("Paraná", d), *d.groupby("meso")]:
            m = g.groupby("cod_ibge").agg(p_frost=("frost", "mean"), p_def=("deficit", "mean"), obs=("failure", "mean"))
            m["loss"] = 1 - (1 - m["p_frost"]) * (1 - m["p_def"])
            flag = (g["frost"] > 0) | (g["deficit"] > 0)
            rows.append(dict(sowing=sowing, mesorregiao=meso, municipios=len(m), n=len(g), obs_failure=g["failure"].mean(),
                             p_frost=m["p_frost"].mean(), p_deficit=m["p_def"].mean(), engine_loss=m["loss"].mean(),
                             failure_if_flag=g.loc[flag, "failure"].mean(), failure_if_not=g.loc[~flag, "failure"].mean(),
                             spearman_municipal=m["loss"].corr(m["obs"], method="spearman") if len(m) > 4 else np.nan))
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "statewide_risk.csv", index=False)
    print(f"\n## 3. Off-season corn climate risk vs PAM failures ({d['ano_pam'].min()}–{d['ano_pam'].max()}), by sowing date\n")
    print(t.to_markdown(index=False, floatfmt=".2f"))
    return t


def engine_section() -> pd.DataFrame:
    from field_shift.core import service as svc
    from field_shift.validation import zarc as Z
    rows = []
    for m in Z.municipalities().itertuples():
        try:
            r = svc.recommend({"lat": m.lat_c, "lon": m.lon_c}, current_rotation="soja__milho_safrinha", include_diagnosis=False)
        except Exception as e:  # noqa: BLE001 (outside the polygon, no data...): counted, not fatal
            rows.append(dict(cod_ibge=str(m.geocodigo), top=None, erro=type(e).__name__))
            continue
        rk = sorted(r["agora"]["ranking"], key=lambda x: -x["nota"])
        cover = next((x for x in rk if x["id"].split("__")[1] in COVERS), None)
        corn = next((x for x in rk if x["id"].split("__")[1].startswith("milho")), None)
        mr = r["agora"]["maior_renda"] or {}
        rows.append(dict(cod_ibge=str(m.geocodigo), top=rk[0]["id"].split("__")[1], top_nota=rk[0]["nota"],
                         best_corn_minus_best_cover=(corn["nota"] - cover["nota"]) if corn and cover else np.nan,
                         top_is_best_income=bool(mr.get("primeira_e_maior_renda")), income_given_up=mr.get("primeira_abaixo_r_ha"),
                         erro=None))
    d = _with_meso(pd.DataFrame(rows))
    d.to_csv(OUT / "statewide_engine_top.csv", index=False)
    ok = d[d["top"].notna()]
    t = (ok.assign(cover=ok["top"].isin(COVERS), corn=ok["top"].str.startswith("milho"))
         .groupby("meso").agg(municipios=("cod_ibge", "size"), corn_first=("corn", "mean"), cover_first=("cover", "mean"),
                                score_gap=("best_corn_minus_best_cover", "median"), top_is_best_income=("top_is_best_income", "mean"),
                                income_given_up=("income_given_up", "median")))
    t.loc["Paraná"] = [len(ok), ok["top"].str.startswith("milho").mean(), ok["top"].isin(COVERS).mean(),
                       ok["best_corn_minus_best_cover"].median(), ok["top_is_best_income"].mean(), ok["income_given_up"].median()]
    print(f"\n## 4. Full engine, option ranked first at the municipality centroid (errors: {d['erro'].notna().sum()})\n")
    print(t.to_markdown(floatfmt=".2f"))
    print(ok["top"].value_counts().to_markdown())
    return t


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    B.set_scope("pr")
    sections = sys.argv[1:] or ["income", "covers", "risk", "engine"]
    for s in sections:
        {"income": income_section, "covers": covers_section, "risk": risk_section, "engine": engine_section}[s]()
