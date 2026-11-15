"""Climate-risk indicators (per POWER point and per crop year).

CROP-YEAR CONVENTION: season Y = 01/07/Y to 30/06/Y+1 (e.g. season 2010 = 2010/11). The `ano` label is Y.
Every window is anchored explicitly (see JANELAS): soybean (Sep–Feb) starts in Y; second-season corn, wheat,
Jun–Jul frost, second-season dry spell etc. fall in Y+1 (same season: soybean Y -> second crop/wheat Y+1).
Complete years: seasons 1991..2024 (34 years; POWER data go to 31/12/2025). 1991–2020 normal = seasons 1991..2019.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

YEARS = list(range(1991, 2025))
NORMAL_YEARS = [a for a in YEARS if a <= 2019]
THRESHOLDS = {"le3": 3.0, "le2": 2.0, "le0": 0.0}
SOWINGS_2ND = {"1501": (1, 15), "0102": (2, 1), "1502": (2, 15), "0103": (3, 1), "1503": (3, 15)}
# cycle: (start_month, start_day, end_month, end_day, offset of the start year relative to Y)
CYCLES = {"soja": (10, 15, 2, 15, 0), "safrinha": (2, 15, 6, 15, 1), "trigo": (5, 1, 9, 30, 1)}


def _window(s: pd.Series | pd.DataFrame, y: int, m0, d0, m1, d1, off: int):
    a = y + off
    b = a + (1 if (m1, d1) < (m0, d0) else 0)
    return s.loc[pd.Timestamp(a, m0, d0):pd.Timestamp(b, m1, d1)]


# ET0 FAO-56
def et0_fao56(df: pd.DataFrame, lat: float, elev: float) -> pd.Series:
    """Daily ET0 (mm/day), FAO-56 Penman-Monteith. df with T2M, T2M_MIN, T2M_MAX, T2MDEW, RH2M, WS2M,
    ALLSKY_SFC_SW_DWN (MJ/m2/day). Soil heat flux G = 0."""
    t, tmin, tmax = df["T2M"], df["T2M_MIN"], df["T2M_MAX"]
    rs = df["ALLSKY_SFC_SW_DWN"]
    u2 = df["WS2M"]
    es = (_svp(tmin) + _svp(tmax)) / 2
    ea = _svp(df["T2MDEW"]).where(df["T2MDEW"].notna(), es * df["RH2M"] / 100)
    ea = ea.clip(upper=es)
    delta = 4098 * _svp(t) / (t + 237.3) ** 2
    p = 101.3 * ((293 - 0.0065 * elev) / 293) ** 5.26
    gamma = 0.000665 * p
    # extraterrestrial radiation
    doy = df.index.dayofyear.values
    phi = math.radians(lat)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    ra = pd.Series(ra, index=df.index)
    rso = (0.75 + 2e-5 * elev) * ra
    rns = 0.77 * rs
    frac = (rs / rso).clip(0.3, 1.0)
    sig = 4.903e-9
    rnl = sig * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * np.sqrt(ea)) * (1.35 * frac - 0.35)
    rn = rns - rnl
    num = 0.408 * delta * rn + gamma * 900 / (t + 273) * u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * u2)
    return (num / den).clip(lower=0)


def _svp(t):
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


# Helpers
def _max_seq(arr: np.ndarray, cond: np.ndarray) -> float:
    """Longest run of consecutive days with cond True (NaN in the data breaks the run)."""
    best = cur = 0
    for c in cond:
        cur = cur + 1 if c else 0
        best = max(best, cur)
    return float(best)


def _rain_onset(p: pd.Series, y: int) -> float:
    """Days since 01/09/Y of the first day with >=20 mm in 3 days (day, day+1, day+2) with no dry spell >=10 d
    (P<1 mm) in the following 30 days (day+3..day+32). Searches up to 31/01. NaN if there is none."""
    start = pd.Timestamp(y, 9, 1)
    s = p.loc[start:pd.Timestamp(y + 1, 3, 5)]
    if len(s) < 100:
        return np.nan
    v = s.values
    n_search = (pd.Timestamp(y + 1, 1, 31) - start).days + 1
    for d in range(min(n_search, len(v) - 33)):
        w = v[d:d + 3]
        if np.isnan(w).any() or w.sum() < 20:
            continue
        pos = v[d + 3:d + 33]
        if _max_seq(pos, (pos < 1)) < 10:
            return float(d)
    return np.nan


# Per point
def point_indicators(df: pd.DataFrame, lat: float, elev: float) -> dict[str, dict[int, float]]:
    df = df.sort_index()
    df = df.loc["1991-01-01":"2025-12-31"]
    et0 = et0_fao56(df, lat, elev)
    p = df["PRECTOTCORR"]
    tmin, tmax = df["T2M_MIN"], df["T2M_MAX"]
    out: dict[str, dict[int, float]] = {}

    def put(nome, y, val):
        out.setdefault(nome, {})[y] = val

    for y in YEARS:
        # second-season frost by sowing date
        for tag, (m, d) in SOWINGS_2ND.items():
            sow_date = pd.Timestamp(y + 1, m, d)
            w = tmin.loc[sow_date + pd.Timedelta(days=60): sow_date + pd.Timedelta(days=120)]
            for suf, lim in THRESHOLDS.items():
                put(f"geada_safrinha_semeadura_{tag}_{suf}", y, float((w <= lim).any()) if w.notna().sum() > 40 else np.nan)
        # geada trigo 15/08–30/09 (Y+1) e jun–jul (Y+1)
        wt = _window(tmin, y, 8, 15, 9, 30, 1)
        wj = _window(tmin, y, 6, 1, 7, 31, 1)
        for suf, lim in THRESHOLDS.items():
            put(f"geada_trigo_{suf}", y, float((wt <= lim).any()))
            put(f"geada_junjul_{suf}", y, float((wj <= lim).any()))
        # veranico
        for nome, args in {"safrinha": (3, 1, 4, 30, 1), "soja": (12, 1, 2, 28, 0)}.items():
            ws = _window(p, y, *args)
            if args[3] == 28:  # end of February: use the real last day
                ws = p.loc[pd.Timestamp(y, 12, 1): pd.Timestamp(y + 1, 3, 1) - pd.Timedelta(days=1)]
            mx = _max_seq(ws.values, (ws < 1).values)
            put(f"veranico_maxseq_{nome}", y, mx)
            put(f"veranico_{nome}_ge10", y, float(mx >= 10))
            put(f"veranico_{nome}_ge15", y, float(mx >= 15))
        # calor soja
        wc = tmax.loc[pd.Timestamp(y, 12, 1): pd.Timestamp(y + 1, 1, 31)]
        nd = float((wc >= 35).sum())
        put("calor_soja_dias", y, nd)
        put("calor_soja_ge5", y, float(nd >= 5))
        # rain onset
        put("inicio_chuvas_dias_desde_0109", y, _rain_onset(p, y))
        # chuva intensa, chuva mensal (safra jul Y..jun Y+1)
        ps = p.loc[pd.Timestamp(y, 7, 1): pd.Timestamp(y + 1, 6, 30)]
        put("chuva_intensa_dias_ge50", y, float((ps >= 50).sum()))
        put("chuva_ano_agricola_mm", y, float(ps.sum()))
        monthly = ps.groupby(ps.index.month).sum()
        for m, v in monthly.items():
            put(f"chuva_mensal_mm_m{m:02d}", y, float(v))
        # ciclos
        for c, (m0, d0, m1, d1, off) in CYCLES.items():
            pw = _window(p, y, m0, d0, m1, d1, off)
            ew = _window(et0, y, m0, d0, m1, d1, off)
            tw = _window(df, y, m0, d0, m1, d1, off)
            put(f"chuva_{c}_mm", y, float(pw.sum()))
            put(f"et0_{c}_mm", y, float(ew.sum()))
            put(f"balanco_p_et0_{c}_mm", y, float(pw.sum() - ew.sum()))
            gd = (((tw["T2M_MAX"] + tw["T2M_MIN"]) / 2) - 10).clip(lower=0).sum()
            put(f"graus_dia_{c}", y, float(gd))
            put(f"gwetroot_{c}", y, float(tw["GWETROOT"].mean()))
    return out


def _aggregate(g: pd.DataFrame) -> pd.Series:
    v = g["valor"].dropna()
    n = g[g.ano.isin(NORMAL_YEARS)]["valor"].dropna()
    return pd.Series(dict(
        n_anos=len(v), media=v.mean(), mediana=v.median(), p20=v.quantile(.2), p80=v.quantile(.8),
        media_1991_2020=n.mean(), mediana_1991_2020=n.median(), p20_1991_2020=n.quantile(.2),
        p80_1991_2020=n.quantile(.8)))


def build_indicators(proc: Path):
    df = pd.read_parquet(proc / "power_diario.parquet")
    pts = df.groupby("ponto_id").agg(tipo=("tipo", "first"), cod_ibge=("cod_ibge", "first"),
                                     lat=("lat", "first"), lon=("lon", "first"), elev=("elev", "first"))
    lines = []
    for pid, g in df.groupby("ponto_id"):
        info = pts.loc[pid]
        g = g.set_index("data")
        res = point_indicators(g, float(info.lat), float(info.elev))
        for ind, series in res.items():
            for year, v in series.items():
                lines.append((pid, ind, year, v))
        print(f"indicadores {pid}", flush=True) if pid.startswith("cel_-25.000_-53.7500") else None
    annual_value = pd.DataFrame(lines, columns=["ponto_id", "indicador", "ano", "valor"])
    annual_value = annual_value.merge(pts.reset_index(), on="ponto_id")
    annual_value["valor"] = annual_value["valor"].astype("float32")
    annual_value[["ponto_id", "tipo", "cod_ibge", "lat", "lon", "ano", "indicador", "valor"]].to_parquet(
        proc / "indicadores_anuais.parquet", index=False)
    agg = (annual_value.groupby(["ponto_id", "indicador"])[["ano", "valor"]].apply(_aggregate).reset_index())
    agg = agg.merge(pts.reset_index(), on="ponto_id")
    agg.to_parquet(proc / "indicadores.parquet", index=False)
    print(f"indicadores_anuais: {len(annual_value)} rows; indicadores: {len(agg)} rows "
          f"({agg.indicador.nunique()} indicators, {agg.ponto_id.nunique()} points)")
