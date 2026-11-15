"""Indicadores de risco climático (por ponto POWER e por ano agrícola).

CONVENÇÃO DE ANO AGRÍCOLA: safra Y = 01/07/Y a 30/06/Y+1 (ex.: safra 2010 = 2010/11). O rótulo `ano` é Y.
Toda janela é ancorada explicitamente (ver JANELAS): soja (set–fev) começa em Y; safrinha, trigo,
geada jun–jul, veranico safrinha etc. caem em Y+1 (mesma safra: soja Y -> safrinha/trigo Y+1).
Anos completos: safras 1991..2024 (34 anos; dados POWER vão até 31/12/2025). Normal 1991–2020 = safras 1991..2019.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

ANOS = list(range(1991, 2025))
ANOS_NORMAL = [a for a in ANOS if a <= 2019]
LIMIARES = {"le3": 3.0, "le2": 2.0, "le0": 0.0}
SEMEADURAS = {"1501": (1, 15), "0102": (2, 1), "1502": (2, 15), "0103": (3, 1), "1503": (3, 15)}
# ciclo: (mês_ini, dia_ini, mês_fim, dia_fim, offset do ano de início em relação a Y)
CICLOS = {"soja": (10, 15, 2, 15, 0), "safrinha": (2, 15, 6, 15, 1), "trigo": (5, 1, 9, 30, 1)}


def _janela(s: pd.Series | pd.DataFrame, y: int, m0, d0, m1, d1, off: int):
    a = y + off
    b = a + (1 if (m1, d1) < (m0, d0) else 0)
    return s.loc[pd.Timestamp(a, m0, d0):pd.Timestamp(b, m1, d1)]


# ----------------------------------------------------------------------------- ET0 FAO-56
def et0_fao56(df: pd.DataFrame, lat: float, elev: float) -> pd.Series:
    """ET0 diária (mm/dia), Penman-Monteith FAO-56. df com T2M, T2M_MIN, T2M_MAX, T2MDEW, RH2M, WS2M,
    ALLSKY_SFC_SW_DWN (MJ/m2/dia). Fluxo de calor do solo G = 0."""
    t, tmin, tmax = df["T2M"], df["T2M_MIN"], df["T2M_MAX"]
    rs = df["ALLSKY_SFC_SW_DWN"]
    u2 = df["WS2M"]
    es = (_svp(tmin) + _svp(tmax)) / 2
    ea = _svp(df["T2MDEW"]).where(df["T2MDEW"].notna(), es * df["RH2M"] / 100)
    ea = ea.clip(upper=es)
    delta = 4098 * _svp(t) / (t + 237.3) ** 2
    p = 101.3 * ((293 - 0.0065 * elev) / 293) ** 5.26
    gamma = 0.000665 * p
    # radiação extraterrestre
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


# ----------------------------------------------------------------------------- helpers
def _max_seq(arr: np.ndarray, cond: np.ndarray) -> float:
    """Maior sequência consecutiva de dias com cond True (NaN no dado quebra a sequência)."""
    best = cur = 0
    for c in cond:
        cur = cur + 1 if c else 0
        best = max(best, cur)
    return float(best)


def _inicio_chuvas(p: pd.Series, y: int) -> float:
    """Dias desde 01/09/Y do primeiro dia com >=20 mm em 3 dias (dia, dia+1, dia+2) sem veranico >=10 d
    (P<1 mm) nos 30 dias seguintes (dia+3..dia+32). Busca até 31/01. NaN se não houver."""
    ini = pd.Timestamp(y, 9, 1)
    s = p.loc[ini:pd.Timestamp(y + 1, 3, 5)]
    if len(s) < 100:
        return np.nan
    v = s.values
    n_busca = (pd.Timestamp(y + 1, 1, 31) - ini).days + 1
    for d in range(min(n_busca, len(v) - 33)):
        w = v[d:d + 3]
        if np.isnan(w).any() or w.sum() < 20:
            continue
        pos = v[d + 3:d + 33]
        if _max_seq(pos, (pos < 1)) < 10:
            return float(d)
    return np.nan


# ----------------------------------------------------------------------------- por ponto
def indicadores_ponto(df: pd.DataFrame, lat: float, elev: float) -> dict[str, dict[int, float]]:
    df = df.sort_index()
    df = df.loc["1991-01-01":"2025-12-31"]
    et0 = et0_fao56(df, lat, elev)
    p = df["PRECTOTCORR"]
    tmin, tmax, tm = df["T2M_MIN"], df["T2M_MAX"], df["T2M"]
    gwr = df["GWETROOT"]
    out: dict[str, dict[int, float]] = {}

    def put(nome, y, val):
        out.setdefault(nome, {})[y] = val

    seca = p < 1
    for y in ANOS:
        # geada safrinha por semeadura
        for tag, (m, d) in SEMEADURAS.items():
            sem = pd.Timestamp(y + 1, m, d)
            w = tmin.loc[sem + pd.Timedelta(days=60): sem + pd.Timedelta(days=120)]
            for suf, lim in LIMIARES.items():
                put(f"geada_safrinha_semeadura_{tag}_{suf}", y, float((w <= lim).any()) if w.notna().sum() > 40 else np.nan)
        # geada trigo 15/08–30/09 (Y+1) e jun–jul (Y+1)
        wt = _janela(tmin, y, 8, 15, 9, 30, 1)
        wj = _janela(tmin, y, 6, 1, 7, 31, 1)
        for suf, lim in LIMIARES.items():
            put(f"geada_trigo_{suf}", y, float((wt <= lim).any()))
            put(f"geada_junjul_{suf}", y, float((wj <= lim).any()))
        # veranico
        for nome, args in {"safrinha": (3, 1, 4, 30, 1), "soja": (12, 1, 2, 28, 0)}.items():
            ws = _janela(p, y, *args)
            if args[3] == 28:  # fim de fevereiro: usa último dia real
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
        # início das chuvas
        put("inicio_chuvas_dias_desde_0109", y, _inicio_chuvas(p, y))
        # chuva intensa, chuva mensal (safra jul Y..jun Y+1)
        ps = p.loc[pd.Timestamp(y, 7, 1): pd.Timestamp(y + 1, 6, 30)]
        put("chuva_intensa_dias_ge50", y, float((ps >= 50).sum()))
        put("chuva_ano_agricola_mm", y, float(ps.sum()))
        mensal = ps.groupby(ps.index.month).sum()
        for m, v in mensal.items():
            put(f"chuva_mensal_mm_m{m:02d}", y, float(v))
        # ciclos
        for c, (m0, d0, m1, d1, off) in CICLOS.items():
            pw = _janela(p, y, m0, d0, m1, d1, off)
            ew = _janela(et0, y, m0, d0, m1, d1, off)
            tw = _janela(df, y, m0, d0, m1, d1, off)
            put(f"chuva_{c}_mm", y, float(pw.sum()))
            put(f"et0_{c}_mm", y, float(ew.sum()))
            put(f"balanco_p_et0_{c}_mm", y, float(pw.sum() - ew.sum()))
            gd = (((tw["T2M_MAX"] + tw["T2M_MIN"]) / 2) - 10).clip(lower=0).sum()
            put(f"graus_dia_{c}", y, float(gd))
            put(f"gwetroot_{c}", y, float(tw["GWETROOT"].mean()))
    return out


def _agrega(g: pd.DataFrame) -> pd.Series:
    v = g["valor"].dropna()
    n = g[g.ano.isin(ANOS_NORMAL)]["valor"].dropna()
    return pd.Series(dict(
        n_anos=len(v), media=v.mean(), mediana=v.median(), p20=v.quantile(.2), p80=v.quantile(.8),
        media_1991_2020=n.mean(), mediana_1991_2020=n.median(), p20_1991_2020=n.quantile(.2),
        p80_1991_2020=n.quantile(.8)))


def gerar_indicadores(proc: Path):
    df = pd.read_parquet(proc / "power_diario.parquet")
    pts = df.groupby("ponto_id").agg(tipo=("tipo", "first"), cod_ibge=("cod_ibge", "first"),
                                     lat=("lat", "first"), lon=("lon", "first"), elev=("elev", "first"))
    linhas = []
    for pid, g in df.groupby("ponto_id"):
        info = pts.loc[pid]
        g = g.set_index("data")
        res = indicadores_ponto(g, float(info.lat), float(info.elev))
        for ind, serie in res.items():
            for ano, v in serie.items():
                linhas.append((pid, ind, ano, v))
        print(f"indicadores {pid}", flush=True) if pid.startswith("cel_-25.000_-53.7500") else None
    anual = pd.DataFrame(linhas, columns=["ponto_id", "indicador", "ano", "valor"])
    anual = anual.merge(pts.reset_index(), on="ponto_id")
    anual["valor"] = anual["valor"].astype("float32")
    anual[["ponto_id", "tipo", "cod_ibge", "lat", "lon", "ano", "indicador", "valor"]].to_parquet(
        proc / "indicadores_anuais.parquet", index=False)
    agg = (anual.groupby(["ponto_id", "indicador"])[["ano", "valor"]].apply(_agrega).reset_index())
    agg = agg.merge(pts.reset_index(), on="ponto_id")
    agg.to_parquet(proc / "indicadores.parquet", index=False)
    print(f"indicadores_anuais: {len(anual)} linhas; indicadores: {len(agg)} linhas "
          f"({agg.indicador.nunique()} indicadores, {agg.ponto_id.nunique()} pontos)")
