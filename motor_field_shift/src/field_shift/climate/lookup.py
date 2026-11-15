"""Lookup of precomputed climate indicators (Paraná) by lat/lon + NASA POWER fallback.

indicators_for(lat, lon) -> dict | None. None if the point is outside the region.
fallback_power(lat, lon)  -> dict | None. Queries NASA POWER (1991-2025) live, in the same format.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from field_shift.climate.indicators import point_indicators

ROOT = Path(__file__).resolve().parents[3]
PROC = ROOT / "data/processed/clima_pr"
MUN = ROOT / "data/raw/clima_pr/municipios_pr.geojson"
DLAT, DLON = 0.5, 0.625
STATS = ["n_anos", "media", "mediana", "p20", "p80", "media_1991_2020", "mediana_1991_2020",
         "p20_1991_2020", "p80_1991_2020"]

POWER_PARAMS = (
    "T2M,T2M_MIN,T2M_MAX,PRECTOTCORR,RH2M,"
    "WS2M,ALLSKY_SFC_SW_DWN,T2MDEW,GWETTOP,GWETROOT"
)
POWER_START = "19910101"
POWER_END = "20251231"


@lru_cache(maxsize=1)
def _dados():
    ind = pd.read_parquet(PROC / "indicadores.parquet")
    by_point = {pid: g for pid, g in ind.groupby("ponto_id")}
    mun = gpd.read_file(MUN)
    return by_point, mun


def cell_id(lat: float, lon: float) -> str:
    return f"cel_{round(lat / DLAT) * DLAT:+.3f}_{round(lon / DLON) * DLON:+.4f}"


def _point_dict(g: pd.DataFrame) -> dict:
    out = {}
    for r in g.itertuples(index=False):
        d = {k: (None if pd.isna(getattr(r, k)) else float(getattr(r, k))) for k in STATS}
        if r.indicador == "inicio_chuvas_dias_desde_0109":
            for k in ("mediana", "p80", "p20"):
                if d[k] is not None:
                    dt = date(2001, 9, 1) + timedelta(days=int(round(d[k])))
                    d[f"{k}_ddmm"] = dt.strftime("%d/%m")
        out[r.indicador] = d
    return out


def indicators_for(lat: float, lon: float) -> dict | None:
    if not (PROC / "indicadores.parquet").exists() or not MUN.exists():
        return None
    by_point, mun = _dados()
    pt = Point(lon, lat)
    hit = mun[mun.geometry.contains(pt)]
    if hit.empty:
        return None
    m = hit.iloc[0]
    cid = cell_id(lat, lon)
    mid = f"mun_{m.cod_ibge}"
    if cid not in by_point or mid not in by_point:
        return None
    gc = by_point[cid].iloc[0]
    return dict(
        dentro_da_regiao=True,
        celula=dict(ponto_id=cid, lat=float(gc.lat), lon=float(gc.lon), elev=float(gc.elev),
                    indicadores=_point_dict(by_point[cid])),
        municipio=dict(cod_ibge=m.cod_ibge, nome=m.nome, lat=float(m.lat_c), lon=float(m.lon_c),
                       indicadores=_point_dict(by_point[mid])),
        convencao="ano agrícola Y = jul/Y a jun/Y+1; anos 1991-2024; *_1991_2020 = safras 1991-2019",
    )


def _series_stats(nome: str, s_all: pd.Series, s_ref: pd.Series) -> dict:
    def _compute(s: pd.Series) -> tuple[float, float, float, float]:
        if s.empty:
            return (np.nan, np.nan, np.nan, np.nan)
        return (
            float(s.mean()),
            float(s.median()),
            float(np.percentile(s, 20)),
            float(np.percentile(s, 80)),
        )

    m, med, p20, p80 = _compute(s_all)
    m91, med91, p20_91, p80_91 = _compute(s_ref)
    return {
        "indicador": nome,
        "n_anos": float(len(s_all)),
        "media": m,
        "mediana": med,
        "p20": p20,
        "p80": p80,
        "media_1991_2020": m91,
        "mediana_1991_2020": med91,
        "p20_1991_2020": p20_91,
        "p80_1991_2020": p80_91,
    }


def _aggregate_fallback(annual_ind: pd.DataFrame | dict) -> pd.DataFrame:
    df = pd.DataFrame(annual_ind) if isinstance(annual_ind, dict) else annual_ind.copy()

    if "indicador" in df.columns:
        val_col = "valor" if "valor" in df.columns else [
            c for c in df.columns if c not in ("indicador", "ano_agricola", "safra", "ano")
        ][0]
        year_col = next((c for c in ("ano_agricola", "safra", "ano") if c in df.columns), None)
        lines = []
        for ind_nome, g in df.groupby("indicador"):
            s_all = pd.to_numeric(g[val_col], errors="coerce").dropna()
            s_ref = (
                pd.to_numeric(g.loc[g[year_col] <= 2019, val_col], errors="coerce").dropna()
                if year_col else s_all.iloc[:29]
            )
            lines.append(_series_stats(str(ind_nome), s_all, s_ref))
        return pd.DataFrame(lines)

    year_col = next((c for c in ("ano_agricola", "safra", "ano") if c in df.columns), None)
    if year_col is not None:
        years = pd.to_numeric(df[year_col], errors="coerce")
        ind_cols = [c for c in df.columns if c != year_col]
    else:
        years = pd.to_numeric(pd.Series(df.index, index=df.index), errors="coerce")
        ind_cols = list(df.columns)

    lines = []
    for col in ind_cols:
        s_num = pd.to_numeric(df[col], errors="coerce")
        s_all = s_num.dropna()
        s_ref = s_num[years <= 2019].dropna() if not years.isna().all() else s_all.iloc[:29]
        lines.append(_series_stats(str(col), s_all, s_ref))
    return pd.DataFrame(lines)


@lru_cache(maxsize=32)
def _download_power_cache(lat_cell: float, lon_cell: float) -> tuple[pd.DataFrame | None, float | None]:
    url = (
        f"https://power.larc.nasa.gov/api/temporal/daily/point"
        f"?parameters={POWER_PARAMS}&community=AG"
        f"&longitude={lon_cell:.4f}&latitude={lat_cell:.3f}"
        f"&start={POWER_START}&end={POWER_END}&format=JSON"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "FieldShift-Engine/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None, None

    coords = payload.get("geometry", {}).get("coordinates", [])
    param_date = payload.get("properties", {}).get("parameter", {})
    if len(coords) < 3 or not param_date:
        return None, None

    elev = float(coords[2])
    df = pd.DataFrame(param_date)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "data"
    df = df.sort_index().replace([-999, -999.0], np.nan)
    return df, elev


def fallback_power(lat: float, lon: float) -> dict | None:
    """Download NASA POWER (1991-2025) for the point's cell and compute indicators in the indicators_for format."""
    lat_cell = round(lat / DLAT) * DLAT
    lon_cell = round(lon / DLON) * DLON
    df, elev = _download_power_cache(lat_cell, lon_cell)
    if df is None or df.empty or elev is None:
        return None

    annual_ind = point_indicators(df, lat=lat_cell, elev=elev)
    df_agg = _aggregate_fallback(annual_ind)
    cid = cell_id(lat, lon)

    return dict(
        dentro_da_regiao=False,
        celula=dict(ponto_id=cid, lat=float(lat_cell), lon=float(lon_cell), elev=float(elev),
                    indicadores=_point_dict(df_agg)),
        municipio=None,
        convencao="ano agrícola Y = jul/Y a jun/Y+1; anos 1991-2024; *_1991_2020 = safras 1991-2019",
    )